import asyncio
from functools import lru_cache
from typing import Any

from app.config import Settings

def build_modal_payload(settings: Settings, messages: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "model": settings.modal_llm_model,
        "messages": [
            {"role": "system", "content": settings.system_prompt},
            *messages,
        ],
        "max_tokens": settings.llm_max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def build_gemini_contents(messages: list[dict[str, str]]) -> list[Any]:
    from google.genai import types

    return [
        types.Content(
            role="model" if message["role"] == "assistant" else "user",
            parts=[types.Part(text=message["content"])],
        )
        for message in messages
    ]


@lru_cache(maxsize=4)
def _gemini_client(project: str, location: str) -> Any:
    from google import genai
    from google.genai.types import HttpOptions

    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=HttpOptions(api_version="v1"),
    )


def _generate_with_gemini(settings: Settings, messages: list[dict[str, str]]) -> str:
    from google.genai.types import GenerateContentConfig

    client = _gemini_client(
        settings.google_cloud_project,
        settings.google_cloud_location,
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=build_gemini_contents(messages),
        config=GenerateContentConfig(
            system_instruction=settings.system_prompt,
            max_output_tokens=settings.llm_max_tokens,
        ),
    )
    return (response.text or "").strip()


async def generate_reply(settings: Settings, messages: list[dict[str, str]]) -> str:
    if settings.llm_provider == "gemini":
        return await asyncio.to_thread(_generate_with_gemini, settings, messages)

    import httpx

    payload = build_modal_payload(settings, messages)
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        response = await client.post(
            f"{settings.modal_llm_url}/v1/chat/completions",
            json=payload,
        )
        response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return str(content).strip()