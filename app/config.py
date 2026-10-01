import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    llm_provider: str
    system_prompt: str
    gemini_api_key: str
    gemini_model: str
    google_cloud_project: str
    google_cloud_location: str
    modal_llm_url: str
    modal_llm_model: str
    modal_proxy_token_id: str
    modal_proxy_token_secret: str
    modal_max_requests_per_month: int
    embedding_provider: str
    llm_timeout_seconds: float
    llm_max_tokens: int
    valkey_url: str
    session_max_turns: int
    session_ttl: int
    knowledge_dir: str
    qdrant_url: str
    qdrant_collection: str
    embedding_model: str
    embedding_dimensions: int
    chunk_size: int
    chunk_overlap: int
    rag_top_k: int
    rag_min_score: float
    rag_context_max_chars: int


def get_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "gemini-api").strip().lower()
    if provider not in {"gemini-api", "gemini", "modal"}:
        raise RuntimeError("LLM_PROVIDER phải là 'gemini-api', 'gemini' hoặc 'modal'.")
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()
    if embedding_provider not in {"local", "vertex"}:
        raise RuntimeError("EMBEDDING_PROVIDER phải là 'local' hoặc 'vertex'.")

    settings = Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        llm_provider=provider,
        system_prompt=os.getenv(
            "BOT_SYSTEM_PROMPT",
            "You are a helpful, general-purpose assistant. Answer clearly and accurately. "
            "Respond in the user's language. If you are unsure, say so instead of inventing facts.",
        ),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        google_cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        modal_llm_url=os.getenv("MODAL_LLM_URL", "").rstrip("/"),
        modal_llm_model=os.getenv("MODAL_LLM_MODEL", "Qwen/Qwen3-4B-Instruct-2507"),
        modal_proxy_token_id=os.getenv("MODAL_PROXY_TOKEN_ID", "").strip(),
        modal_proxy_token_secret=os.getenv("MODAL_PROXY_TOKEN_SECRET", "").strip(),
        modal_max_requests_per_month=int(os.getenv("MODAL_MAX_REQUESTS_PER_MONTH", "400")),
        embedding_provider=embedding_provider,
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "512")),
        valkey_url=os.getenv("VALKEY_URL", "redis://localhost:6379/0"),
        session_max_turns=int(os.getenv("SESSION_MAX_TURNS", "10")),
        session_ttl=int(os.getenv("SESSION_TTL", "86400")),
        knowledge_dir=os.getenv("KNOWLEDGE_DIR", "knowledge"),
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "cloud_bot_knowledge"),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL",
            "intfloat/multilingual-e5-small" if embedding_provider == "local" else "gemini-embedding-001",
        ),
        embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "384" if embedding_provider == "local" else "768")),
        chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "1200")),
        chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "160")),
        rag_top_k=int(os.getenv("RAG_TOP_K", "5")),
        rag_min_score=float(os.getenv("RAG_MIN_SCORE", "0.35")),
        rag_context_max_chars=int(os.getenv("RAG_CONTEXT_MAX_CHARS", "10000")),
    )

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN chưa được cấu hình.")
    if provider == "gemini-api" and not settings.gemini_api_key:
        raise RuntimeError("Cần GEMINI_API_KEY khi dùng Gemini Developer API.")
    if provider == "gemini" and not settings.google_cloud_project:
        raise RuntimeError("Cần GOOGLE_CLOUD_PROJECT khi LLM_PROVIDER=gemini.")
    if embedding_provider == "vertex" and not settings.google_cloud_project:
        raise RuntimeError("Cần GOOGLE_CLOUD_PROJECT khi EMBEDDING_PROVIDER=vertex.")
    if provider == "modal" and not settings.modal_llm_url:
        raise RuntimeError("Cần MODAL_LLM_URL khi LLM_PROVIDER=modal.")
    if provider == "modal" and not settings.modal_proxy_token_id:
        raise RuntimeError("Cần MODAL_PROXY_TOKEN_ID khi LLM_PROVIDER=modal.")
    if provider == "modal" and not settings.modal_proxy_token_secret:
        raise RuntimeError("Cần MODAL_PROXY_TOKEN_SECRET khi LLM_PROVIDER=modal.")
    if settings.modal_max_requests_per_month < 1:
        raise RuntimeError("MODAL_MAX_REQUESTS_PER_MONTH phải lớn hơn 0.")
    if settings.session_max_turns < 1 or settings.session_ttl < 1:
        raise RuntimeError("SESSION_MAX_TURNS và SESSION_TTL phải lớn hơn 0.")
    if settings.embedding_dimensions < 1:
        raise RuntimeError("EMBEDDING_DIMENSIONS phải lớn hơn 0.")
    if settings.chunk_size < 1 or not 0 <= settings.chunk_overlap < settings.chunk_size:
        raise RuntimeError("RAG_CHUNK_OVERLAP phải >= 0 và nhỏ hơn RAG_CHUNK_SIZE.")
    if settings.rag_top_k < 1 or settings.rag_context_max_chars < 1:
        raise RuntimeError("RAG_TOP_K và RAG_CONTEXT_MAX_CHARS phải lớn hơn 0.")
    if not 0 <= settings.rag_min_score <= 1:
        raise RuntimeError("RAG_MIN_SCORE phải nằm trong khoảng 0..1.")

    return settings