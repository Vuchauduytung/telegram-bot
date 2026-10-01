import os

import modal

app = modal.App("test-modal")

image = (
    modal.Image.debian_slim()
    .pip_install("requests")
)


@app.function(image=image)
def test_llm(modal_llm_url: str):

    import requests
    import time

    payload = {
        "model": "Qwen/Qwen3.6-35B-A3B-FP8",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant. Answer concisely."
            },
            {
                "role": "user",
                "content": "Explain what a Docker container is in two sentences."
            }
        ],
        "max_tokens": 128,
        "stream": False,
        "chat_template_kwargs": {
            "enable_thinking": False
        }
    }

    start = time.perf_counter()

    response = requests.post(
        f"{modal_llm_url.rstrip('/')}/v1/chat/completions",
        json=payload,
        timeout=120,
    )

    elapsed = time.perf_counter() - start

    response.raise_for_status()

    data = response.json()

    return {
        "response": data["choices"][0]["message"]["content"],
        "latency_seconds": elapsed,
        "usage": data.get("usage"),
    }


@app.local_entrypoint()
def main():
    from dotenv import load_dotenv

    load_dotenv()
    modal_llm_url = os.getenv("MODAL_LLM_URL", "").rstrip("/")
    if not modal_llm_url:
        raise RuntimeError("Set MODAL_LLM_URL in the environment or .env file.")

    result = test_llm.remote(modal_llm_url)

    print("=" * 60)
    print("LLM Response")
    print("=" * 60)
    print(result["response"])

    print("\n" + "=" * 60)
    print("Performance")
    print("=" * 60)

    print(f"Latency: {result['latency_seconds']:.3f}s")
    print(f"Usage:   {result['usage']}")