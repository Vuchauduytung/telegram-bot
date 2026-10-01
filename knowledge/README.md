# Knowledge Base

Add UTF-8 Markdown (`.md`) or plain text (`.txt`) files here. The bot mounts this directory read-only; index updates are made by running the ingestion command.

From the project directory, index or update all supported files with:

```bash
docker compose -f compose.yaml -f compose.modal.yaml run --rm bot python -m app.ingest
```

Use `compose.gemini.yaml` instead of `compose.modal.yaml` when the bot is configured for Gemini generation. Each document is chunked and embedded with Vertex AI, then stored in Qdrant with its relative filename and title for citations. Re-running ingestion replaces the indexed chunks for each source instead of duplicating them.

Remove one source from the index with:

```bash
docker compose -f compose.yaml -f compose.modal.yaml run --rm bot python -m app.ingest --delete-source example.md
```

The directory contains a small operations guide for checking retrieval end to end. Replace or supplement it with the knowledge sources intended for this bot.