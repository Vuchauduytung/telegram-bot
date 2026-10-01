# Deployment Checklist

This checklist targets the Telegram polling bot and Qdrant RAG stack. The recommended profile uses Gemini Developer API free tier with local embeddings; free-tier quotas and data terms still apply.

Related docs: [README.md](README.md) and [FEATURES_RAG.md](FEATURES_RAG.md).

## 1. Release Readiness

- [ ] Confirm the release commit/tag and review the diff; do not deploy an unreviewed working tree.
- [ ] Run the bot tests and syntax check:

  ```bash
  PYTHONPATH=. python tests/test_llm.py
  PYTHONPATH=. python tests/test_rag.py
  PYTHONPATH=. python tests/test_modal_quota.py
  python -m compileall -q app tests
  ```

- [ ] Build the container successfully with `docker compose build bot`.
- [ ] Confirm the deployment target, owner, maintenance window, rollback version, and expected monthly budget.
- [ ] Confirm the bot will use polling. This deployment does not require an inbound Telegram webhook or public bot port.

## 2. Host and Network

- [ ] Use a supported Linux host with Docker Engine and the Docker Compose plugin.
- [ ] Reserve enough disk space for container images, Valkey data, logs, and backups.
- [ ] Allow outbound HTTPS to Telegram and the selected generation provider; allow internal bot-to-Valkey/Qdrant traffic on the Compose network.
- [ ] Do not expose Valkey or the bot container ports publicly. Polling requires outbound access only.
- [ ] Configure host restart and disk monitoring; verify the host clock is synchronized.

## 3. Secrets and Provider

- [ ] Create `.env` from `.env.example` on the host; set restrictive permissions, for example `chmod 600 .env`.
- [ ] Set `BOT_TOKEN` from BotFather. Never commit it, put it in an image, or include it in logs.
- [ ] Select exactly one backend using `LLM_PROVIDER` and configure only the credentials needed for it.
- [ ] Set a deliberate `BOT_SYSTEM_PROMPT`, model, timeout, token limit, and session TTL.
- [ ] Check `docker compose config --quiet` before starting containers.

### Gemini Developer API Free Tier

- [ ] Create a Gemini API key in Google AI Studio and store it as `GEMINI_API_KEY` in `.env` with restrictive file permissions.
- [ ] Use `compose.free-tier.yaml`; do not configure Vertex ADC or Modal credentials for this profile.
- [ ] Confirm the selected model's current free-tier availability, quota, region, and data-use terms in Google's pricing page.
- [ ] Define handling for 429/quota-exhausted responses; free tier has limits and is not unlimited.

### Optional Paid Vertex AI

- [ ] Enable Vertex AI for the selected Google Cloud project and confirm billing/quota are available.
- [ ] Provide Application Default Credentials or workload identity to the bot process with only the required Vertex AI permissions.
- [ ] For Docker Compose, use `compose.gemini.yaml` to mount the host ADC file read-only; set `GOOGLE_APPLICATION_CREDENTIALS_FILE` if it is not at the default gcloud path. A host-only `gcloud auth application-default login` is not automatically visible to the container.
- [ ] Set `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `GEMINI_MODEL` in the bot environment.
- [ ] Run `python test-gemini.py` from `cloud-bot` in an environment with the same identity and project to smoke-test direct Vertex access.

### Modal-hosted model

- [ ] Confirm GPU availability, quotas, model revision, cold-start time, and monthly spend before deploying `modal_llm.py`.
- [ ] Review the low-cost Modal profile: Qwen3 4B-Instruct FP16 on L4, `min_containers=0`, `max_containers=1`, 8K context, and 60-second scale-down.
- [ ] Budget against current Modal rates: L4 is listed at `$0.000222/GPU-second`; with 4 vCPU and 16 GiB RAM, `$30` covers at most about 26.9 fully loaded hours before other usage. Starter credits are not a hard spend cap; monitor usage and configure billing controls.
- [ ] Confirm the bot's atomic Valkey quota is set to 400 Modal generation attempts per UTC month. It fails closed if Valkey is down; direct endpoint calls with the Proxy Token bypass this app-level quota.
- [ ] Cloud Functions do not attach GPUs. If evaluating Google's GPU option, compare Cloud Run L4 (at least 4 vCPU/16 GiB; GPU billed for full instance lifetime even though it can scale to zero) against the Modal profile.
- [ ] Confirm `modal_llm.py` keeps `unauthenticated=False`; Modal proxy authentication must reject unauthenticated requests with HTTP 401.
- [ ] Create a dedicated proxy token with `modal workspace proxy-tokens create --name cloud-bot-bot`. If workspace RBAC is enabled, allow it only in the deployment environment. The secret is shown once; store `ID.SECRET` as `MODAL_PROXY_TOKEN` in `.env` with mode `0600`.
- [ ] Deploy the private model service with `modal deploy modal_llm.py` and record its base URL as `MODAL_ENDPOINT_URL` in `.env`, without adding `/v1/chat/completions`.
- [ ] Verify `.env` is ignored by Git. The older `.env.modal` split-key variables are supported only as a compatibility fallback.
- [ ] Run `python test-modal.py` and confirm response text and latency before starting the Telegram bot.
- [ ] Start the bot with `docker compose -f compose.yaml -f compose.modal.yaml up -d --build` and verify authenticated provider access from inside the container.
- [ ] Confirm Modal returns to zero active containers after the 60-second idle window; send one smoke request, verify cold-start behavior, then confirm it scales down.

## 4. Deploy the Current Bot

- [ ] Transfer only the reviewed source and required runtime configuration to the host. Exclude `.env`, credentials, virtual environments, and caches.
- [ ] Start Valkey and the bot:

  ```bash
  docker compose -f compose.yaml -f compose.gemini.yaml up -d --build
  docker compose ps
  docker compose logs --tail=100 bot
  ```

- [ ] Confirm both services remain running and the bot can reach Valkey.
- [ ] Confirm the selected LLM provider is reachable using the same identity, URL, and network path as the running container.
- [ ] Send `/start`, `/help`, `/reset`, a normal question, and a follow-up question in Telegram.
- [ ] Restart the bot container and confirm the chat still works; when Valkey is healthy, confirm recent history survives the restart.
- [ ] Test an unavailable LLM response and verify the bot returns a useful error without logging the user's full prompt.
- [ ] Verify logs do not contain bot tokens, cloud credentials, Modal secrets, or other sensitive data.

## 5. Persistence, Monitoring, and Operations

- [ ] Confirm the `valkey-data` volume exists and is not accidentally recreated or removed during routine upgrades.
- [ ] Define a backup and restore procedure for Valkey data if conversation history must survive host loss.
- [ ] Set log rotation and disk usage limits for Docker.
- [ ] Monitor bot restarts, Valkey availability, LLM errors/latency, host disk, and provider spend.
- [ ] Set billing budgets/alerts for Google Cloud and Modal; verify who receives the alerts.
- [ ] Document who can rotate `BOT_TOKEN`, cloud credentials, and the Modal endpoint URL.
- [ ] Rehearse a restart and a restore on a non-production instance before relying on the service.

## 6. Rollback

- [ ] Keep the last known-good release tag/image and its matching configuration version.
- [ ] If the new bot release is unhealthy, restore the previous source/image and run `docker compose up -d --build bot`.
- [ ] Preserve Valkey data during rollback. Do not run `docker compose down -v` unless data deletion is intentional and approved.
- [ ] If a provider credential or endpoint may be exposed, revoke/rotate it first, then update the bot configuration and restart.
- [ ] Verify `/start`, a normal message, and session continuity after rollback.

## 7. RAG Operations and Remaining Gates

The current stack includes Markdown/TXT ingestion, local multilingual-E5 embeddings in the free profile, Qdrant dense retrieval, context assembly, and source citations. Hybrid retrieval, reranking, deterministic abstention, and automated evaluation are still outstanding.

- [x] Add Qdrant to Compose with persistent storage and no published host ports.
- [x] Confirm ingestion is idempotent; sample corpus stayed at two points after re-ingest.
- [x] Re-index documents and verify the embedding model/dimension match query and index vectors.
- [ ] Define and test Qdrant backup/restore and collection migration.
- [ ] Run an automated RAG evaluation set. Review Recall@k/MRR, groundedness, citation correctness, and no-answer behavior against agreed thresholds.
- [ ] Verify user/tenant filters are enforced in retrieval before any multi-user private corpus is loaded.
- [ ] Confirm source text and prompts are excluded from ordinary logs; document retention and deletion behavior.
- [x] Smoke-test a supported question through retrieval and generation; verify citation points to retrieved filename.
- [ ] Smoke-test unsupported questions, follow-ups, and source updates/deletions against production policy.
- [ ] Enable RAG for a small canary audience first; monitor retrieval misses, false citations, latency, and cost before widening access.
- [ ] Keep a rollback path that can disable retrieval or return to the non-RAG bot without deleting the document index.

## Go / No-Go

- [ ] **Go** only when release tests pass, secrets and provider access are verified, spend is approved, smoke tests pass, and rollback is available.
- [ ] **No-go for Modal production** unless the deployed inference endpoint rejects requests without a valid proxy token.
- [ ] **No-go for high-confidence grounded-answer claims** until deterministic abstention and evaluation thresholds are implemented and accepted.