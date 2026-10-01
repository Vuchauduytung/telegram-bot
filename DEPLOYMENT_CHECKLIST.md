# Deployment Checklist

This checklist targets the current Telegram polling bot deployed with Docker Compose on a Linux host. It also includes a separate release gate for the planned RAG stack. Checking items off is an operator action; this file does not mean a deployment has already happened.

Related docs: [README.md](README.md) and [FEATURES_RAG.md](FEATURES_RAG.md).

## 1. Release Readiness

- [ ] Confirm the release commit/tag and review the diff; do not deploy an unreviewed working tree.
- [ ] Run the bot tests and syntax check:

  ```bash
  PYTHONPATH=. python tests/test_llm.py
  python -m compileall -q app tests
  ```

- [ ] Build the container successfully with `docker compose build bot`.
- [ ] Confirm the deployment target, owner, maintenance window, rollback version, and expected monthly budget.
- [ ] Confirm the bot will use polling. This deployment does not require an inbound Telegram webhook or public bot port.

## 2. Host and Network

- [ ] Use a supported Linux host with Docker Engine and the Docker Compose plugin.
- [ ] Reserve enough disk space for container images, Valkey data, logs, and backups.
- [ ] Allow outbound HTTPS to Telegram and to the selected LLM provider; allow internal bot-to-Valkey traffic on the Compose network.
- [ ] Do not expose Valkey or the bot container ports publicly. Polling requires outbound access only.
- [ ] Configure host restart and disk monitoring; verify the host clock is synchronized.

## 3. Secrets and Provider

- [ ] Create `.env` from `.env.example` on the host; set restrictive permissions, for example `chmod 600 .env`.
- [ ] Set `BOT_TOKEN` from BotFather. Never commit it, put it in an image, or include it in logs.
- [ ] Select exactly one backend using `LLM_PROVIDER` and configure only the credentials needed for it.
- [ ] Set a deliberate `BOT_SYSTEM_PROMPT`, model, timeout, token limit, and session TTL.
- [ ] Check `docker compose config --quiet` before starting containers.

### Gemini on Vertex AI

- [ ] Enable Vertex AI for the selected Google Cloud project and confirm billing/quota are available.
- [ ] Provide Application Default Credentials or workload identity to the bot process with only the required Vertex AI permissions.
- [ ] For Docker Compose, use `compose.gemini.yaml` to mount the host ADC file read-only; set `GOOGLE_APPLICATION_CREDENTIALS_FILE` if it is not at the default gcloud path. A host-only `gcloud auth application-default login` is not automatically visible to the container.
- [ ] Set `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `GEMINI_MODEL` in the bot environment.
- [ ] Run `python test-gemini.py` from `cloud-bot` in an environment with the same identity and project to smoke-test direct Vertex access.

### Modal-hosted model

- [ ] Confirm GPU availability, quotas, model revision, expected cold-start time, and cost before deploying `modal_llm.py`.
- [ ] Review the current Modal configuration: it requests an H100, keeps `MIN_CONTAINERS=1`, and has a 30-minute scaledown window. Confirm this always-warm GPU cost is intentional.
- [ ] **Do not use the current endpoint as a production public service without adding access control.** `modal_llm.py` sets `unauthenticated=True`; anyone who obtains its URL can send inference requests. Add an authenticated gateway or equivalent restriction, then update the bot client to send and verify credentials before production use.
- [ ] Deploy the model service with `modal deploy modal_llm.py` and record its base URL in the secret environment configuration, without adding `/v1/chat/completions`.
- [ ] Set `LLM_PROVIDER=modal`, `MODAL_LLM_URL`, and the exact served `MODAL_LLM_MODEL`.
- [ ] Run `modal run test-modal.py` and confirm response text and latency before starting the Telegram bot.

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

## 7. Additional Gate Before Enabling RAG

The current deployment does **not** include document ingestion, embeddings, Qdrant, retrieval, citations, or RAG evaluation. Do not claim that answers are grounded in uploaded documents until these gates are complete.

- [ ] Implement the P0 items in [FEATURES_RAG.md](FEATURES_RAG.md), including ingestion, stable chunk metadata, embedding provider, Qdrant, retrieval, citations, and abstention.
- [ ] Add Qdrant to the deployment with persistent storage, health checks, network isolation, backup/restore, and a documented collection migration strategy.
- [ ] Confirm ingestion is idempotent; verify source updates and deletions remove stale chunks.
- [ ] Re-index a representative corpus and verify embedding model, vector dimensions, and query/index preprocessing match.
- [ ] Run the RAG evaluation set. Review retrieval Recall@k/MRR, groundedness, citation correctness, and no-answer behavior against agreed thresholds.
- [ ] Verify user/tenant filters are enforced in retrieval before any multi-user private corpus is loaded.
- [ ] Confirm source text and prompts are excluded from ordinary logs; document retention and deletion behavior.
- [ ] Smoke-test a supported question, an unsupported question, a follow-up question, and a source update against the deployed RAG pipeline.
- [ ] Enable RAG for a small canary audience first; monitor retrieval misses, false citations, latency, and cost before widening access.
- [ ] Keep a rollback path that can disable retrieval or return to the non-RAG bot without deleting the document index.

## Go / No-Go

- [ ] **Go** only when release tests pass, secrets and provider access are verified, spend is approved, smoke tests pass, and rollback is available.
- [ ] **No-go for Modal production** while the inference endpoint remains unauthenticated and publicly callable.
- [ ] **No-go for RAG claims** until the additional RAG gate above is complete and evaluation results are accepted.