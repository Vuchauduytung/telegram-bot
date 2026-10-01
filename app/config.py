import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    llm_provider: str
    system_prompt: str
    gemini_model: str
    google_cloud_project: str
    google_cloud_location: str
    modal_llm_url: str
    modal_llm_model: str
    llm_timeout_seconds: float
    llm_max_tokens: int
    valkey_url: str
    session_max_turns: int
    session_ttl: int


def get_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    if provider not in {"gemini", "modal"}:
        raise RuntimeError("LLM_PROVIDER phải là 'gemini' hoặc 'modal'.")

    settings = Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        llm_provider=provider,
        system_prompt=os.getenv(
            "BOT_SYSTEM_PROMPT",
            "You are a helpful, general-purpose assistant. Answer clearly and accurately. "
            "Respond in the user's language. If you are unsure, say so instead of inventing facts.",
        ),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        google_cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        modal_llm_url=os.getenv("MODAL_LLM_URL", "").rstrip("/"),
        modal_llm_model=os.getenv("MODAL_LLM_MODEL", "Qwen/Qwen3.6-35B-A3B-FP8"),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1024")),
        valkey_url=os.getenv("VALKEY_URL", "redis://localhost:6379/0"),
        session_max_turns=int(os.getenv("SESSION_MAX_TURNS", "10")),
        session_ttl=int(os.getenv("SESSION_TTL", "86400")),
    )

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN chưa được cấu hình.")
    if provider == "gemini" and not settings.google_cloud_project:
        raise RuntimeError("Cần GOOGLE_CLOUD_PROJECT khi LLM_PROVIDER=gemini.")
    if provider == "modal" and not settings.modal_llm_url:
        raise RuntimeError("Cần MODAL_LLM_URL khi LLM_PROVIDER=modal.")
    if settings.session_max_turns < 1 or settings.session_ttl < 1:
        raise RuntimeError("SESSION_MAX_TURNS và SESSION_TTL phải lớn hơn 0.")

    return settings