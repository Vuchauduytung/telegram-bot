# General-purpose Telegram AI bot

Telegram polling bot that can use Gemini on Vertex AI or the OpenAI-compatible LLM endpoint served by `modal_llm.py`. Both providers receive the same system prompt and recent per-chat conversation history.

## Configure

Create a Telegram bot with [@BotFather](https://t.me/BotFather), then copy `.env.example` to `.env` and set `BOT_TOKEN`.

Choose one backend:

- **Gemini:** set `LLM_PROVIDER=gemini` and `GOOGLE_CLOUD_PROJECT`. Authenticate with Application Default Credentials, for example `gcloud auth application-default login`. The selected identity needs access to Vertex AI.
- **Modal:** deploy the existing server with `modal deploy modal_llm.py`, set `LLM_PROVIDER=modal`, and set `MODAL_LLM_URL` to its base URL (without `/v1/chat/completions`). Set `MODAL_LLM_MODEL` to the served model name if it differs from the default. The example server currently exposes an unauthenticated public endpoint; keep its URL private because anyone with it can submit requests that consume GPU time.

`BOT_SYSTEM_PROMPT`, model names, request timeout, token limit, session length, and session TTL can also be changed in `.env`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d valkey
python -m app.main
```

When Valkey is unavailable, the bot keeps session history in process memory until it restarts.

## Run with Docker Compose

```bash
cp .env.example .env
docker compose -f compose.yaml -f compose.gemini.yaml up -d --build
docker compose logs -f bot
```

The Gemini Compose override mounts the host ADC file read-only at runtime. Set `GOOGLE_APPLICATION_CREDENTIALS_FILE` to a different host file path when needed. Do not add service-account keys to the project or commit them. For Modal mode, use the base `compose.yaml`; it only needs the bot token and Modal endpoint URL.

## Conversation commands

- `/start` starts a fresh conversation.
- `/help` lists commands.
- `/reset` clears the current chat's history.

## Test

```bash
PYTHONPATH=. python tests/test_llm.py
python -m compileall -q app tests
```