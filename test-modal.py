import os
import time

import httpx
from dotenv import load_dotenv


def main() -> None:
    load_dotenv(".env.modal")
    modal_llm_url = os.getenv("MODAL_LLM_URL", "").rstrip("/")
    modal_proxy_token_id = os.getenv("MODAL_PROXY_TOKEN_ID", "")
    modal_proxy_token_secret = os.getenv("MODAL_PROXY_TOKEN_SECRET", "")
    if not all((modal_llm_url, modal_proxy_token_id, modal_proxy_token_secret)):
        raise RuntimeError(
            "Set MODAL_LLM_URL, MODAL_PROXY_TOKEN_ID, and "
            "MODAL_PROXY_TOKEN_SECRET in .env.modal."
        )

    payload = {
        "model": os.getenv("MODAL_LLM_MODEL", "Qwen/Qwen3.6-35B-A3B-FP8"),
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Answer concisely."},
            {
                "role": "user",
                "content": "Explain what a Docker container is in two sentences.",
            },
        ],
        "max_tokens": 128,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    start = time.perf_counter()
    response = httpx.post(
        f"{modal_llm_url}/v1/chat/completions",
        headers={
            "Modal-Key": modal_proxy_token_id,
            "Modal-Secret": modal_proxy_token_secret,
        },
        json=payload,
        timeout=120,
    )
    elapsed = time.perf_counter() - start
    response.raise_for_status()
    data = response.json()

    print("=" * 60)
    print("LLM Response")
    print("=" * 60)
    print(data["choices"][0]["message"]["content"])

    print("\n" + "=" * 60)
    print("Performance")
    print("=" * 60)
    print(f"Latency: {elapsed:.3f}s")
    print(f"Usage:   {data.get('usage')}")


if __name__ == "__main__":
    main()