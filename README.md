# General-purpose Telegram AI bot

Telegram polling bot that can use Gemini on Vertex AI or the OpenAI-compatible LLM endpoint served by `modal_llm.py`. Both providers receive the same system prompt and recent per-chat conversation history.

The bot also retrieves relevant Markdown/TXT sources from Qdrant, embeds documents and queries with Vertex AI, and appends source citations to answers when evidence is found.

## Configure

Create a Telegram bot with [@BotFather](https://t.me/BotFather), then copy `.env.example` to `.env` and set `BOT_TOKEN`.

Choose one backend:

- **Gemini:** set `LLM_PROVIDER=gemini` and `GOOGLE_CLOUD_PROJECT`. Authenticate with Application Default Credentials, for example `gcloud auth application-default login`. The selected identity needs access to Vertex AI.
- **Modal:** copy `.env.modal.example` to `.env.modal`, create a dedicated proxy token with `modal workspace proxy-tokens create --name cloud-bot-bot`, and save its ID and secret in `.env.modal`. Deploy `modal_llm.py`; it requires Modal proxy authentication. Put the deployment's base URL (without `/v1/chat/completions`) in `MODAL_LLM_URL` in `.env.modal`. The token secret is shown only once by Modal; keep `.env.modal` private and never commit it.

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
docker compose -f compose.yaml -f compose.gemini.yaml up -d --build
docker compose logs -f bot
```

The Gemini Compose override mounts the host ADC file read-only at runtime. Set `GOOGLE_APPLICATION_CREDENTIALS_FILE` to a different host file path when needed. Do not add service-account keys to the project or commit them. For Modal mode, configure `.env.modal` and run:

```bash
docker compose -f compose.yaml -f compose.modal.yaml up -d --build
```

Both Compose modes start Qdrant with a persistent volume and mount `./knowledge` read-only. Vertex ADC is used for embeddings even when Modal is selected for answer generation.

## RAG Knowledge Base

Add UTF-8 `.md` or `.txt` documents to `knowledge/`. Ingestion chunks each source, creates `gemini-embedding-001` vectors through Vertex AI, and upserts metadata and vectors into the private Qdrant service. The bot retrieves the top matching chunks before generation and includes source filenames in its reply. Re-ingesting a changed document replaces its previous chunks.

With the Modal deployment:

```bash
docker compose -f compose.yaml -f compose.modal.yaml run --rm bot python -m app.ingest
```

With Gemini generation, replace `compose.modal.yaml` with `compose.gemini.yaml`. Remove an indexed source by its path relative to `knowledge/`:

```bash
docker compose -f compose.yaml -f compose.modal.yaml run --rm bot python -m app.ingest --delete-source cloud_bot_guide.md
```

Settings for collection name, embedding dimensions, chunk size/overlap, top-k, minimum relevance, and context budget are in `.env.example`. Changing embedding model or dimensions requires re-indexing into a collection with matching vector dimensions. PDF/URL ingestion, hybrid search, reranking, and automated RAG evaluation are not implemented yet.

## Conversation commands

- `/start` starts a fresh conversation.
- `/help` lists commands.
- `/reset` clears the current chat's history.

## Test

```bash
PYTHONPATH=. python tests/test_llm.py
PYTHONPATH=. python tests/test_rag.py
python -m compileall -q app tests
python test-modal.py
```