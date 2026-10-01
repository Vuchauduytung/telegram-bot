# Cloud Bot Operations Guide

The Telegram bot supports `/start`, `/help`, and `/reset`. The `/reset` command clears the current chat's conversation history.

Conversation history is stored separately from reference documents. Valkey keeps recent messages per chat; Qdrant stores indexed knowledge chunks and their source metadata.

The document index accepts UTF-8 Markdown and TXT files. Run `python -m app.ingest` to add or update sources. Answers supported by indexed documents should cite the source filename shown in the answer.

The bot can generate answers with Gemini on Vertex AI or with the private OpenAI-compatible model endpoint on Modal. The Modal endpoint requires its Proxy Token credentials; do not share those credentials or endpoint configuration publicly.