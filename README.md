# General-purpose Telegram AI bot

Telegram AI bot with local polling and a production Cloud Run webhook profile. The no-per-request-charge profile uses the Gemini Developer API free tier for generation, local multilingual-E5 embeddings, Qdrant retrieval, and Valkey conversation history. A private Modal GPU profile is also available for local Qwen generation when its extra compute cost is acceptable.

The bot retrieves relevant Markdown/TXT sources from Qdrant and appends source citations to answers. Default profiles use local embeddings; Vertex AI embeddings are an optional paid configuration.

For the production webhook deployment, see the [Cloud Run deployment guide](CLOUD_RUN_DEPLOYMENT_GUIDE.md). The polling and Compose instructions below are for local development and self-hosted deployments.

For a planned migration from Telegram to Rainbow by ALE, see the [Rainbow setup guide](RAINBOW_SETUP_GUIDE.md). Rainbow integration is not implemented in the current bot yet.

## Configure

Create a Telegram bot with [@BotFather](https://t.me/BotFather), then copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` (the legacy `BOT_TOKEN` name is still accepted).

## Free-tier profile (recommended)

Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey), then put it in `.env` as `GEMINI_API_KEY`. Do not send or commit the key. The free tier has model- and account-specific quotas/rate limits, is not unlimited, and its data-use terms differ from the paid tier. Check [current pricing and free-tier details](https://ai.google.dev/gemini-api/docs/pricing) before production use.

The free profile uses `gemini-3.5-flash-lite` for answers and `intfloat/multilingual-e5-small` on the bot host for embeddings. The local embedding model has no per-request API charge; first use downloads its weights and consumes local CPU/RAM/disk. Vertex ADC is not needed by this profile.

## Optional paid providers

- **Vertex AI:** set `LLM_PROVIDER=gemini` or `EMBEDDING_PROVIDER=vertex`, configure `GOOGLE_CLOUD_PROJECT`, and provide ADC. These requests are billed to Google Cloud; Gemini API free-tier quotas do not apply.
- **Modal low-cost GPU:** set `MODAL_ENDPOINT_URL` and `MODAL_PROXY_TOKEN` in `.env`; the token format is `wk-token-id.ws-token-secret`. The legacy `.env.modal` URL and split token fields remain accepted. The profile uses Qwen3 4B-Instruct in FP16 on an L4, scales to zero (`min_containers=0`), caps at one container, and scales down after 60 idle seconds. Cold starts are expected; no GPU stays warm while idle.

`BOT_SYSTEM_PROMPT`, model names, request timeout, token limit, session length, and session TTL can also be changed in `.env`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d valkey qdrant
python -m app.main
```

When Valkey is unavailable, the bot keeps session history in process memory until it restarts.

## Run with Docker Compose

```bash
cp .env.example .env
docker compose -f compose.yaml -f compose.free-tier.yaml up -d --build
docker compose logs -f bot
```

This profile requires `GEMINI_API_KEY` in `.env`; it does not mount Google Cloud credentials or call Vertex AI. Qdrant and Valkey run locally in Compose with persistent volumes.

For paid Vertex generation/embedding, use `compose.gemini.yaml`; it mounts host ADC read-only. For Modal generation, set `MODAL_ENDPOINT_URL` and `MODAL_PROXY_TOKEN` in `.env` and run:

```bash
docker compose -f compose.yaml -f compose.modal.yaml up -d --build
```

As of October 2026, Modal lists L4 at `$0.000222/GPU-second`. With this profile's 4 vCPU and 16 GiB RAM, `$30/month` Starter compute credits cover at most about **26.9 fully loaded hours** before any other usage; actual serving time will be lower. This is an estimate, not a hard spending cap. The bot additionally allows at most **400 Modal generation attempts per UTC month**, reserved before sending the request (failed attempts count), and fails closed if Valkey is unavailable. This protects bot traffic, not direct use of the private Proxy Token; `python test-modal.py` bypasses the bot counter. Monitor Modal usage and keep the token private.

Google **Cloud Functions** does not attach GPUs. Google **Cloud Run services** support L4 GPUs and scale to zero, but require at least 4 vCPU and 16 GiB RAM, and bill the GPU for the instance's full lifetime. For this small, bursty budget, Modal's per-second GPU billing is the chosen optional profile; Cloud Run is a valid alternative if its full instance cost fits the budget.

All Compose modes start local Qdrant/Valkey containers with persistent volumes and mount `./knowledge` read-only. Leave `QDRANT_URL` and `VALKEY_URL` blank to use those local services. To use managed services, set the Qdrant HTTPS URL plus `QDRANT_API_KEY`, and the Valkey `rediss://` URL plus `VALKEY_TOKEN`; Compose passes these credentials through to the clients. `GITHUB_TOKEN` and `HF_TOKEN` are optional integration/download credentials, not needed for normal bot traffic. The free and Modal profiles run embeddings locally. Vertex-mode embeddings require ADC.

## RAG Knowledge Base

Add UTF-8 `.md` or `.txt` documents to `knowledge/`. In the free profile, ingestion chunks each source, creates 384-dimensional multilingual-E5 vectors locally, and upserts metadata and vectors into the private Qdrant service. The bot retrieves top matching chunks before generation and includes source filenames in its reply. Re-ingesting a changed document replaces its previous chunks.

With the Modal deployment (`MODAL_ENDPOINT_URL` and `MODAL_PROXY_TOKEN` in `.env`):

```bash
docker compose -f compose.yaml -f compose.modal.yaml run --rm bot python -m app.ingest
```

For the free profile, replace `compose.modal.yaml` with `compose.free-tier.yaml`. Its separate Qdrant collection avoids mixing 384-dimensional local vectors with the previous 768-dimensional Vertex vectors. Remove an indexed source by its path relative to `knowledge/`:

```bash
docker compose -f compose.yaml -f compose.modal.yaml run --rm bot python -m app.ingest --delete-source cloud_bot_guide.md
```

Settings for collection name, embedding dimensions, chunk size/overlap, top-k, minimum relevance, and context budget are in `.env.example`. Changing embedding model or dimensions requires a new collection and full re-index. PDF/URL ingestion, hybrid search, reranking, and automated RAG evaluation are not implemented yet.

## Conversation commands

- `/start` starts a fresh conversation.
- `/help` lists commands.
- `/reset` clears the current chat's history.

## Test

```bash
PYTHONPATH=. python tests/test_llm.py
PYTHONPATH=. python tests/test_rag.py
python -m compileall -q app tests
```