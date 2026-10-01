import time

import httpx
from dotenv import dotenv_values


def main() -> None:
    env = dotenv_values(".env.modal")
    env.update({key: value for key, value in dotenv_values(".env").items() if value})
    modal_llm_url = (env.get("MODAL_ENDPOINT_URL") or env.get("MODAL_LLM_URL") or "").rstrip("/")
    proxy_token = env.get("MODAL_PROXY_TOKEN") or ""
    modal_proxy_token_id, separator, modal_proxy_token_secret = proxy_token.partition(".")
    if not separator:
        modal_proxy_token_id = env.get("MODAL_PROXY_TOKEN_ID") or ""
        modal_proxy_token_secret = env.get("MODAL_PROXY_TOKEN_SECRET") or ""
    if not all((modal_llm_url, modal_proxy_token_id, modal_proxy_token_secret)):
        raise RuntimeError(
            "Set MODAL_ENDPOINT_URL and MODAL_PROXY_TOKEN in .env."
        )

    payload = {
        "model": env.get("MODAL_LLM_MODEL") or "Qwen/Qwen3-4B-Instruct-2507",
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
        timeout=600,
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