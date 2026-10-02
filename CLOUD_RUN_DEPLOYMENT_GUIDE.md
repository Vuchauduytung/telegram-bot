# Cloud Run Webhook Deployment Guide

This guide deploys the production Telegram webhook service. It is separate from the polling-based local Docker Compose workflow in the README and deployment checklist.

## Deployment Profile

| Setting | Value |
| --- | --- |
| GCP region | `australia-southeast1` |
| Cloud Run service | `cloud-bot-telegram` |
| Runtime | FastAPI/Uvicorn, port 8080 |
| CPU and memory | 2 vCPU, 2 GiB |
| Scaling | Minimum 0, maximum 1 instance |
| Concurrency and timeout | 10 requests, 300 seconds |
| LLM | Gemini Developer API, `gemini-3.5-flash-lite` |
| Embeddings | Local `intfloat/multilingual-e5-small`, 384 dimensions |
| Vector store | Qdrant collection `cloud_bot_knowledge_e5` |
| Session/cache | Managed Valkey over TLS |

Gemini free-tier access and model availability can change. Check the current [Gemini pricing and free-tier page](https://ai.google.dev/gemini-api/docs/pricing) before deployment. A GCP budget alert does not enforce a spending cap.

## 1. Prerequisites

- Install and authenticate `gcloud`; select an active GCP project with billing enabled.
- Use a project where you can enable APIs, create service accounts/secrets, deploy Cloud Run, and configure the source-build permissions described below.
- From the repository root, create a local `.env` using `.env.example`. Set the Telegram token, webhook secret, Gemini key, Qdrant URL/API key, and Valkey URL/token.
- Keep `.env` private:

  ```bash
  chmod 600 .env
  git check-ignore -q .env
  ```

- Verify Cloud Build's source archive excludes credentials before every source deployment:

  ```bash
  if gcloud meta list-files-for-upload . | grep -Eq '(^|/)\.env(\.modal)?$'; then
    echo 'ERROR: an environment file would be uploaded' >&2
    exit 1
  else
    echo 'Environment files are excluded from the source archive.'
  fi
  ```

Never deploy with `--set-env-vars` values copied from `.env` for secret fields. Use Secret Manager references instead.

## 2. Test the Source

Run the relevant tests in the same dependency image used by the bot:

```bash
docker compose -f compose.yaml -f compose.free-tier.yaml run --rm --no-deps \
  -v "$PWD/app:/app/app:ro" -v "$PWD/tests:/app/tests:ro" bot sh -c \
  'PYTHONPATH=/app python /app/tests/test_webhook.py && \
   PYTHONPATH=/app python /app/tests/test_llm.py && \
   PYTHONPATH=/app python /app/tests/test_rag.py && \
   PYTHONPATH=/app python /app/tests/test_modal_quota.py'
```

For managed Qdrant, put its HTTPS URL and API key in `.env`, then ingest the knowledge directory:

```bash
docker compose -f compose.yaml -f compose.free-tier.yaml run --build --rm --no-deps \
  bot python -m app.ingest
```

The ingestion command reports indexed and failed documents. Stop if any documents failed. Confirm the configured collection name and embedding dimension match the app environment before deploying.

## 3. Enable APIs and Create the Runtime Identity

Set deployment variables in the shell. Replace the project ID with your target project:

```bash
export PROJECT_ID='your-gcp-project-id'
export REGION='australia-southeast1'
export SERVICE='cloud-bot-telegram'
export RUNTIME_SA="cloud-bot-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
```

Confirm project billing and enable required APIs:

```bash
gcloud billing projects describe "$PROJECT_ID"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  --project="$PROJECT_ID"
```

Create the runtime service account once; skip creation if it already exists:

```bash
gcloud iam service-accounts create cloud-bot-runtime \
  --project="$PROJECT_ID" \
  --display-name='Cloud Bot Cloud Run runtime'
```

## 4. Store Credentials in Secret Manager

Create these secret resources once. Skip any secret that already exists:

```bash
gcloud secrets create cloud-bot-telegram-token --project="$PROJECT_ID" --replication-policy=automatic
gcloud secrets create cloud-bot-webhook-secret --project="$PROJECT_ID" --replication-policy=automatic
gcloud secrets create cloud-bot-gemini-api-key --project="$PROJECT_ID" --replication-policy=automatic
gcloud secrets create cloud-bot-qdrant-api-key --project="$PROJECT_ID" --replication-policy=automatic
gcloud secrets create cloud-bot-valkey-url --project="$PROJECT_ID" --replication-policy=automatic
gcloud secrets create cloud-bot-valkey-token --project="$PROJECT_ID" --replication-policy=automatic
```

Upload values from `.env` through stdin; this script prints only secret resource names, never values:

```bash
python - <<'PY'
import subprocess
from dotenv import dotenv_values

project = 'your-gcp-project-id'
values = dotenv_values('.env')
mapping = {
    'TELEGRAM_BOT_TOKEN': 'cloud-bot-telegram-token',
    'WEBHOOK_SECRET': 'cloud-bot-webhook-secret',
    'GEMINI_API_KEY': 'cloud-bot-gemini-api-key',
    'QDRANT_API_KEY': 'cloud-bot-qdrant-api-key',
    'VALKEY_URL': 'cloud-bot-valkey-url',
    'VALKEY_TOKEN': 'cloud-bot-valkey-token',
}
for env_name, secret_name in mapping.items():
    value = (values.get(env_name) or '').strip()
    if not value:
        raise SystemExit(f'{env_name} is empty; no secrets were uploaded.')
    result = subprocess.run(
        ['gcloud', 'secrets', 'versions', 'add', secret_name,
         f'--project={project}', '--data-file=-'],
        input=value,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(f'Upload failed for {secret_name}.')
    print(f'{secret_name}: version added')
PY
```

Grant the runtime identity access to only these six secrets:

```bash
for secret in \
  cloud-bot-telegram-token \
  cloud-bot-webhook-secret \
  cloud-bot-gemini-api-key \
  cloud-bot-qdrant-api-key \
  cloud-bot-valkey-url \
  cloud-bot-valkey-token; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role='roles/secretmanager.secretAccessor'
done
```

For repeatable releases, pin secret references to numeric versions. `latest` is convenient for initial setup but makes the revision's credential version less explicit.

## 5. Deploy the Cloud Run Service

Read the non-secret Qdrant URL from `.env` without printing it, then deploy from the repository root:

```bash
export QDRANT_URL="$(python -c 'from dotenv import dotenv_values; print(dotenv_values(".env")["QDRANT_URL"])')"

gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --cpu 2 \
  --memory 2Gi \
  --min 0 \
  --max 1 \
  --concurrency 10 \
  --timeout 300 \
  --execution-environment gen2 \
  --service-account "$RUNTIME_SA" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},LLM_PROVIDER=gemini-api,EMBEDDING_PROVIDER=local,GEMINI_MODEL=gemini-3.5-flash-lite,QDRANT_URL=${QDRANT_URL},QDRANT_COLLECTION=cloud_bot_knowledge_e5,EMBEDDING_MODEL=intfloat/multilingual-e5-small,EMBEDDING_DIMENSIONS=384,KNOWLEDGE_DIR=/app/knowledge,SESSION_MAX_TURNS=4,SESSION_TTL=86400,LLM_TIMEOUT_SECONDS=60,LLM_MAX_TOKENS=256,RAG_TOP_K=3,RAG_MIN_SCORE=0.35,RAG_CONTEXT_MAX_CHARS=4000,RAG_CHUNK_SIZE=1200,RAG_CHUNK_OVERLAP=160" \
  --set-secrets="TELEGRAM_BOT_TOKEN=cloud-bot-telegram-token:latest,WEBHOOK_SECRET=cloud-bot-webhook-secret:latest,GEMINI_API_KEY=cloud-bot-gemini-api-key:latest,QDRANT_API_KEY=cloud-bot-qdrant-api-key:latest,VALKEY_URL=cloud-bot-valkey-url:latest,VALKEY_TOKEN=cloud-bot-valkey-token:latest"
```

Cloud Run must be publicly reachable by Telegram; the webhook secret header authenticates update requests. The service does not receive Modal credentials unless Modal is deliberately enabled and configured separately.

## 6. Register the Telegram Webhook

Set the public service URL in `.env` as `WEBHOOK_URL` (without `/webhook`), then register it:

```bash
python -m app.set_webhook
```

This calls Telegram `setWebhook` with `secret_token` from `.env`. Keep that value identical to the Secret Manager version referenced by Cloud Run. The registration command prints only a success message.

## 7. Smoke-Test the Deployment

Use the service URL returned by `gcloud run deploy`:

```bash
export SERVICE_URL="$(gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')"
curl -fsS "$SERVICE_URL/health"
```

Confirm a wrong secret is rejected:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  -X POST "$SERVICE_URL/webhook" \
  -H 'Content-Type: application/json' \
  -H 'X-Telegram-Bot-Api-Secret-Token: deliberately-wrong' \
  --data '{}'
```

Expected status: `403`. Then check Telegram webhook state without printing tokens:

```bash
python - <<'PY'
import asyncio
from dotenv import dotenv_values
from telegram import Bot

values = dotenv_values('.env')
async def main():
    async with Bot((values.get('TELEGRAM_BOT_TOKEN') or '').strip()) as bot:
        info = await bot.get_webhook_info()
    expected = (values.get('WEBHOOK_URL') or '').rstrip('/') + '/webhook'
    print('URL matches:', info.url == expected)
    print('Pending updates:', info.pending_update_count)
    print('Delivery error:', 'none' if not info.last_error_message else 'present')
asyncio.run(main())
PY
```

Finally, send `/start` and a normal question to the Telegram bot. Review recent logs if needed:

```bash
gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" --limit=50
```

Use `/health` for health checks. Some Google front-end routes may return 404 for `/healthz` even though the app defines that alias.

## 8. Rotate the Webhook Secret

1. Generate a new value locally and replace `WEBHOOK_SECRET` in `.env`; never paste it into a command, ticket, or chat.
2. Add a Secret Manager version from stdin:

   ```bash
   python -c 'from dotenv import dotenv_values; print(dotenv_values(".env")["WEBHOOK_SECRET"], end="")' \
   | gcloud secrets versions add cloud-bot-webhook-secret \
       --project="$PROJECT_ID" --data-file=-
   ```

3. Note the new numeric version printed by gcloud, then update Cloud Run to reference it:

   ```bash
   gcloud run services update "$SERVICE" \
     --project="$PROJECT_ID" --region="$REGION" \
     --update-secrets=WEBHOOK_SECRET=cloud-bot-webhook-secret:VERSION
   ```

4. After the revision is Ready, run `python -m app.set_webhook` so Telegram sends the new header. Verify webhook status and health again. There may be a brief delivery retry while Cloud Run and Telegram switch versions.

Use the same versioned-secret procedure for rotating other runtime credentials, and redeploy/restart the revision that consumes them.

## 9. Budget, Monitoring, and Rollback

- A monthly `0 VND` GCP budget can notify billing users when GCP spend is detected; it does **not** stop or cap spend. It also does not include independent Qdrant Cloud, Upstash, or Modal charges.
- Watch Cloud Run request/error logs, Gemini quota responses, cold-start latency, and managed-service billing. The free tier is quota-limited and can change.
- To roll back traffic, list revisions, choose the last known-good revision, then route traffic back:

  ```bash
  gcloud run revisions list --service="$SERVICE" --project="$PROJECT_ID" --region="$REGION"
  gcloud run services update-traffic "$SERVICE" \
    --project="$PROJECT_ID" --region="$REGION" \
    --to-revisions="PREVIOUS_REVISION=100"
  ```

- Preserve Qdrant and Valkey data during rollback. Do not delete managed collections or use destructive volume commands as part of a routine release.

## Troubleshooting Source Builds

If Cloud Run source deployment reports `storage.objects.get` denied for the generated `run-sources-...` bucket, grant the build identity `roles/storage.objectViewer` on that bucket only. If Docker build succeeds but image publication is denied, grant `roles/artifactregistry.writer` on the `cloud-run-source-deploy` repository only. Get the actual build identity from `gcloud builds describe BUILD_ID --region="$REGION"`; do not grant broad project Editor roles as a workaround.

If a revision fails to start, check its logs and verify all referenced secret versions exist and the runtime service account has `secretAccessor` on each secret. Do not print or paste secret values while debugging.