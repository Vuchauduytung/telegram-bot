# Rainbow Bot Setup and Telegram Migration Guide

This guide describes how to replace the Telegram transport with **Rainbow by Alcatel-Lucent Enterprise (ALE)** while reusing this repository's Python AI/RAG backend. It is a setup plan, not a claim that Rainbow is already integrated. The deployed `app.webhook` still accepts Telegram `Update` payloads.

## Recommended Architecture

Rainbow's current server-side bot integration is provided by the Node.js SDK. Keep Rainbow's connection/event handling in a Node.js adapter and reuse the Python code for prompts, Gemini, RAG, embeddings, and response formatting:

```text
Rainbow user
    -> Rainbow platform
    -> Node.js Rainbow adapter (SDK connection + chat events)
    -> authenticated internal AI request
    -> Python AI/RAG service (sessions, Qdrant, Gemini/Modal)
    -> Rainbow adapter
    -> Rainbow user
```

The adapter translates Rainbow events into a small platform-neutral request such as `{conversation_id, sender_id, text}`. The Python service returns reply text; the adapter sends it with the Rainbow SDK. Do not POST Rainbow payloads to the existing `/webhook`: it parses Telegram-specific headers and `telegram.Update` objects.

### Choose the Rainbow event transport

| Option | Use when | Operational notes |
| --- | --- | --- |
| Rainbow Node.js SDK in XMPP mode | Recommended default for a normal chatbot | Full real-time SDK path; it maintains a connection and must stay running. A scale-to-zero worker will disconnect while stopped. |
| Rainbow S2S Node.js StarterKit | Only if ALE has enabled S2S for your application and you specifically need callback/webhook events | The developer docs label S2S as restricted/Alpha. Confirm production entitlement, callback delivery/retries, and availability before selecting it. |

Do not use the administrative REST API as a substitute for chat events; ALE documents it primarily for management tasks. Avoid relying on the older `rainbow-chatbot` scenario library for a general LLM bot; use the currently documented Node SDK and implement the message flow explicitly.

## What Can Be Reused

- `app/llm.py`: Gemini/Modal provider selection and shared prompt/RAG policy.
- `app/rag.py`, `app/embeddings.py`, and `app/ingest.py`: retrieval, local E5 embeddings, chunking, and ingestion.
- Existing Qdrant and Valkey services, with the isolation changes below.
- Cloud project, Secret Manager, Artifact Registry, build/test process, and the current Docker-based Python service where appropriate.

## Changes Required Before Rainbow Can Reply

1. **Extract a channel-neutral message service.** Move the work currently performed inside `app.handlers.message_handler` into a function that accepts a conversation ID, sender ID, and text, then returns a reply. Keep thin Telegram handlers only if Telegram must remain available during migration.
2. **Add an authenticated internal interface or shared library.** The Rainbow Node adapter needs a supported way to call the Python message service. Prefer a private Cloud Run service-to-service endpoint with IAM authentication. If the Python service remains public for Telegram, protect any new internal route separately; Cloud Run's public invoker setting applies to the whole service.
3. **Give sessions a platform namespace.** `app/session.py` currently uses fixed `cloud-bot:session:*` and `cloud-bot:modal-requests:*` Redis keys. Add a configurable application namespace, or give Rainbow its own Valkey database, so conversations and Modal quota do not collide with Telegram.
4. **Separate Rainbow knowledge.** Use a collection such as `rainbow_knowledge` and ingest Rainbow-specific Markdown/TXT content. The current `cloud_bot_knowledge_e5` collection contains the existing bot's corpus; do not mix private or unrelated knowledge bases by accident.
5. **Move channel-specific behavior to the adapter.** The Python handlers contain Telegram `Update`, `ContextTypes`, reply methods, and `/start` text. Implement Rainbow welcome/help/reset behavior in the Rainbow adapter, or expose channel-neutral command handling from the backend.

## 1. Create a Rainbow Developer Sandbox

1. Create/sign in to a Rainbow account and register for the Rainbow for Developers portal: [developers.openrainbow.com](https://developers.openrainbow.com/).
2. Accept the developer agreement and activate a **Developer Sandbox** account. Sandbox credentials are distinct from production credentials.
3. In the Sandbox section, create a test application and record its Application ID and Application Secret in a secure password manager.
4. Create or select a sandbox bot user and one or more test users. Confirm they belong to the same sandbox environment/company and can start a direct conversation with the bot.
5. Use sandbox host `sandbox` during development. Do not point sandbox credentials at the official production host.

ALE's developer journey describes account, test-user, and application setup: [Developer's Journey](https://developers.openrainbow.com/doc/hub/developer-journey) and [Application Lifecycle](https://developers.openrainbow.com/doc/hub/application-lifecycle).

## 2. Bootstrap the Node.js Adapter

Use an active Node.js LTS release and npm. From a new adapter directory:

```bash
mkdir rainbow-adapter
cd rainbow-adapter
npm init -y
npm install --save rainbow-node-sdk
```

Do not commit `node_modules`, local credential files, or `.env`. Add the following settings to the adapter's runtime secret/configuration source:

| Variable | Sandbox value |
| --- | --- |
| `RAINBOW_HOST` | `sandbox` |
| `RAINBOW_MODE` | `xmpp` |
| `RAINBOW_LOGIN` | Sandbox bot user's login |
| `RAINBOW_PASSWORD` | Sandbox bot user's password |
| `RAINBOW_APP_ID` | Sandbox application's ID |
| `RAINBOW_APP_SECRET` | Sandbox application's secret |
| `AI_BACKEND_URL` | Private URL for the Python message service |
| `AI_BACKEND_AUTH` | Service-to-service identity/credential; never log it |

Construct the SDK configuration from environment variables at runtime. Do not commit `bot.json` or a config file containing credentials. The SDK configuration uses `rainbow.host`, `rainbow.mode`, `credentials.login/password`, and `application.appID/appSecret`.

Start the SDK and wait for `rainbow_onready` before accepting work. Also handle `rainbow_onconnectionerror`, `rainbow_ondisconnected`, `rainbow_onreconnecting`, `rainbow_onfailed`, and `rainbow_onerror`; log state changes without credentials or message bodies.

Official references: [Node.js SDK getting started](https://developers.openrainbow.com/doc/sdk/node/lts/guides/Getting_Started), [connecting to Rainbow](https://developers.openrainbow.com/doc/sdk/node/lts/guides/Connecting_to_Rainbow_XMPP_Mode), and [answering chat messages](https://developers.openrainbow.com/doc/sdk/node/lts/guides/Answering_chat_message).

## 3. Receive and Reply to Messages

Subscribe to the SDK's `rainbow_onmessagereceived` event. Start with direct messages (`message.type === "chat"`); add bubbles only after direct-message flow is stable. Ignore system/event messages and messages authored by the bot itself to prevent reply loops.

For a direct message:

1. Validate the event and extract the sender JID and text.
2. Build a stable conversation ID from the Rainbow sender/conversation identity; never reuse Telegram chat IDs.
3. Call the authenticated Python message service with conversation ID, sender ID, and text.
4. Send the returned reply with `rainbowSDK.im.sendMessageToJid(reply, message.fromJid)`.

For a bubble (`message.type === "groupchat"`), use the bubble identity and `sendMessageToBubbleJid`. Rainbow documents `fromJid` in a bubble as a room/user identity; do not treat it as a direct-message JID. Filter `isEvent` messages such as member join/leave notifications.

Add idempotency/deduplication for event IDs, bounded retries, and rate limiting. Keep message content and credentials out of routine logs. Review Rainbow's message-size and API limits before forwarding long AI answers; split or summarize replies according to the current SDK/platform limits.

## 4. Deploy the Adapter and Backend

The existing Cloud Run Telegram service is configured for scale-to-zero and its public `/webhook` endpoint is Telegram-specific. It is not a drop-in Rainbow receiver.

For the XMPP Node SDK, deploy the adapter as a long-running worker with a persistent outbound connection. A Cloud Run worker that scales to zero will disconnect; keeping a minimum instance or using an always-on VM changes cost. Validate CPU allocation, shutdown/reconnect behavior, and monthly billing before production. The Python AI backend can remain a separate private Cloud Run service, invoked by the adapter through Cloud Run IAM.

If using the S2S StarterKit instead, configure its callback URL/reverse proxy and verify callback authentication, retries, and cold-start behavior. Do not assume the existing Telegram `WEBHOOK_SECRET` protects Rainbow callbacks; use the authentication mechanism defined by the chosen Rainbow SDK/S2S integration.

Use distinct Secret Manager entries for Rainbow login/password and application credentials, and grant a dedicated adapter service account access only to those secrets. Keep the Python backend's Gemini, Qdrant, and Valkey secrets separate. Do not copy credentials into the image or source archive.

## 5. Isolate Data and Quotas

- **Qdrant:** share the same cluster only if desired; create a distinct Rainbow collection and ingest its approved corpus.
- **Valkey:** either use a separate database/instance or add and test a namespace such as `rainbow:` for sessions, locks, and Modal quota. Current keys are hard-coded with the `cloud-bot:` prefix.
- **Gemini:** a key can technically be reused, but a separate key makes revocation and usage attribution easier. Gemini quotas are shared at the applicable project/key level.
- **Modal:** if reused, ensure the quota is intentionally shared or namespace it per bot. A quota in the Python app does not protect direct calls to a Modal endpoint.
- **GCP budget:** the current zero-VND budget is an alert, not a spending cap; it does not include Rainbow CPaaS charges or separately billed managed providers.

## 6. Sandbox Acceptance Tests

Do not move real users until all of these pass in the Rainbow sandbox:

- SDK reaches `rainbow_onready`, reconnects after a transient network drop, and reports authentication failures clearly.
- A one-to-one message produces exactly one backend request and one Rainbow reply; bot echoes and event messages are ignored.
- `/help`, reset/welcome behavior, session continuity, and a follow-up question work through the Rainbow adapter.
- RAG retrieves from the Rainbow collection and citations identify only retrieved documents.
- Long replies respect Rainbow's current size limits; 429/quota, backend timeout, and Rainbow disconnect cases fail gracefully.
- Session keys are isolated from Telegram and from other Rainbow bots.
- Logs and error traces contain no passwords, application secrets, access tokens, or full private message bodies.

Use the Rainbow client's direct conversation with the sandbox bot account to test. Only after acceptance should you register a production Rainbow application and production bot account.

## 7. Production Cutover

1. Create/register a production application separately from the sandbox application; use its production Application ID/Secret and production bot account credentials.
2. Set the SDK host to `openrainbow.com`. Confirm the application is deployed and in the `RUNNING` state in the Rainbow Developer portal. Business/App Connect offers may require ALE review; Pay As You Go can require a payment method and may incur charges.
3. Store production credentials in Secret Manager and deploy the adapter with the intended always-on/event-callback model.
4. Keep the Telegram bot available during a limited Rainbow pilot if both channels are needed. Ensure namespaces prevent shared-history collisions.
5. Monitor SDK connection state, event counts, backend latency/errors, Rainbow rate limits, Gemini quota, and provider costs. Roll back by routing users back to Telegram or stopping the Rainbow adapter; preserve Qdrant/Valkey data.

Production requirements and offer-specific approval/billing are described in ALE's [Deployment on Production](https://developers.openrainbow.com/doc/hub/get-ready-for-production) and [Application Lifecycle](https://developers.openrainbow.com/doc/hub/application-lifecycle) guides. Confirm current terms and SDK version in the official portal before go-live.

## References

- [Rainbow for Developers](https://developers.openrainbow.com/)
- [Developer's Journey and Sandbox](https://developers.openrainbow.com/doc/hub/developer-journey)
- [Node.js SDK LTS documentation](https://developers.openrainbow.com/doc/sdk/node/home)
- [Incoming and outgoing chat messages](https://developers.openrainbow.com/doc/sdk/node/lts/guides/Answering_chat_message)
- [S2S StarterKit getting started](https://developers.openrainbow.com/doc/sdk/s2s-starterkit-nodejs/guides/Getting_Started)