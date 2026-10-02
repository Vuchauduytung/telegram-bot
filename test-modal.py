import argparse
import sys
import time

import httpx
from dotenv import dotenv_values


def post_with_startup_retry(url: str, headers: dict, payload: dict) -> httpx.Response:
    deadline = time.monotonic() + 300
    next_notice = 0.0

    while True:
        response = httpx.post(url, headers=headers, json=payload, timeout=600)
        if response.status_code != 503:
            return response

        now = time.monotonic()
        remaining = deadline - now
        if remaining <= 0:
            return response

        if now >= next_notice:
            print("Modal is starting (HTTP 503); checking again shortly.")
            next_notice = now + 15
        delay = min(2, remaining)
        time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the Modal LLM endpoint.")
    parser.add_argument(
        "--wait-for-cold-start",
        action="store_true",
        help="Retry HTTP 503 for up to five minutes while Modal starts the model.",
    )
    args = parser.parse_args()

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
            {"role": "user", "content": "Reply with exactly: OK."},
        ],
        "max_tokens": 8,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    start = time.perf_counter()
    url = f"{modal_llm_url}/v1/chat/completions"
    headers = {
        "Modal-Key": modal_proxy_token_id,
        "Modal-Secret": modal_proxy_token_secret,
    }
    if args.wait_for_cold_start:
        response = post_with_startup_retry(url, headers, payload)
    else:
        response = httpx.post(url, headers=headers, json=payload, timeout=45)

    if response.status_code == 503:
        print("Modal is cold-starting and did not become ready for this quick check.")
        print("Run `python test-modal.py --wait-for-cold-start` to wait up to five minutes.")
        sys.exit(1)

    elapsed = time.perf_counter() - start
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        print(f"Modal returned HTTP {error.response.status_code}.")
        sys.exit(1)
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