import subprocess
import time

import modal


# ============================================================
# Configuration
# ============================================================

APP_NAME = "cloud-bot-llm"

MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"
MODEL_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"

PORT = 8000

# Scale to zero when idle; never keep a paid GPU warm.
MIN_CONTAINERS = 0
MAX_CONTAINERS = 1

# One request at a time per replica for low latency.
TARGET_CONCURRENCY = 1

# L4 is the smallest Modal GPU compatible with the current SGLang/CUDA image.
GPU = "L4"


# ============================================================
# Modal volumes
# ============================================================

HF_CACHE_PATH = "/root/.cache/huggingface"
HF_CACHE_VOL = modal.Volume.from_name(
    "cloud-bot-huggingface-cache",
    create_if_missing=True,
)

# ============================================================
# Container image
# ============================================================

image = (
    modal.Image.from_registry(
        "lmsysorg/sglang:v0.5.10.post1-cu130-runtime"
    )
    .entrypoint([])
    .env(
        {
            "HF_HUB_CACHE": HF_CACHE_PATH,
            "HF_XET_HIGH_PERFORMANCE": "1",
            "SGLANG_USE_CUDA_IPC_TRANSPORT": "1",
            "SGLANG_USE_IPC_POOL_HANDLE_CACHE": "1",
        }
    )
)


# ============================================================
# Modal App
# ============================================================

app = modal.App(name=APP_NAME)


# ============================================================
# Helper functions
# ============================================================

def start_sglang():
    """
    Start the OpenAI-compatible SGLang server.
    """

    cmd = [
        "python",
        "-m",
        "sglang.launch_server",

        "--model-path",
        MODEL_NAME,

        "--revision",
        MODEL_REVISION,

        "--served-model-name",
        MODEL_NAME,

        "--dtype",
        "half",

        "--host",
        "0.0.0.0",

        "--port",
        str(PORT),

        # Single GPU
        "--tp",
        "1",

        # Reasoning support for Qwen
        "--reasoning-parser",
        "qwen3",

        # Tool calling support
        "--tool-call-parser",
        "qwen3_coder",

        # Memory usage
        "--mem-fraction-static",
        "0.75",

        # Context length
        "--context-length",
        "8192",

        # Metrics
        "--enable-metrics",
    ]

    print("Starting SGLang:")
    print(" ".join(cmd))

    return subprocess.Popen(
        cmd,
        start_new_session=True,
    )


def wait_for_server(process, timeout=20 * 60):
    """
    Wait until SGLang's /health endpoint is ready.
    """

    import requests

    deadline = time.time() + timeout

    print("Waiting for SGLang server...")

    while time.time() < deadline:

        # Check whether SGLang crashed.
        return_code = process.poll()

        if return_code is not None:
            raise RuntimeError(
                f"SGLang exited during startup with code {return_code}"
            )

        try:
            response = requests.get(
                f"http://127.0.0.1:{PORT}/health",
                timeout=5,
            )

            if response.status_code == 200:
                print("SGLang is ready.")
                return

        except requests.RequestException:
            pass

        time.sleep(5)

    raise TimeoutError(
        f"SGLang did not become ready within {timeout} seconds."
    )


def warmup():
    """
    Send one small request after startup so the first real
    cloud-bot request does not pay additional initialization cost.
    """

    import requests

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": "Say OK.",
            }
        ],
        "max_tokens": 4,
        "stream": False,
    }

    print("Running warmup request...")

    response = requests.post(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        json=payload,
        timeout=120,
    )

    response.raise_for_status()

    print("Warmup complete.")


# ============================================================
# Modal Server
# ============================================================

@app.server(
    image=image,
    gpu=GPU,
    cpu=4,
    memory=16 * 1024,

    volumes={
        HF_CACHE_PATH: HF_CACHE_VOL,
    },

    port=PORT,

    min_containers=MIN_CONTAINERS,
    max_containers=MAX_CONTAINERS,

    # Keep concurrency low for chatbot latency.
    target_concurrency=TARGET_CONCURRENCY,

    # Give Qwen/SGLang enough time to initialize.
    startup_timeout=5 * 60,

    # Accept cold starts to avoid paying for an idle GPU.
    scaledown_window=60,

    # Require Modal Proxy Token authentication at the endpoint.
    unauthenticated=False,
)
class LLMServer:

    @modal.enter()
    def startup(self):

        print("=" * 60)
        print("Starting Cloud Bot LLM")
        print(f"Model: {MODEL_NAME}")
        print(f"GPU: {GPU}")
        print(f"min_containers: {MIN_CONTAINERS}")
        print("=" * 60)

        self.process = start_sglang()

        wait_for_server(self.process)

        warmup()

        print("=" * 60)
        print("Cloud Bot LLM is READY")
        print("=" * 60)

    @modal.exit()
    def shutdown(self):

        print("Stopping SGLang...")

        if self.process.poll() is None:
            self.process.terminate()

            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

        print("SGLang stopped.")


# ============================================================
# Local test
# ============================================================

@app.local_entrypoint()
async def main():

    import requests

    url = await LLMServer.get_url.aio()

    print()
    print("=" * 60)
    print("Server URL:")
    print(url)
    print("=" * 60)

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": "Hello! Who are you?",
            }
        ],
        "max_tokens": 100,
        "stream": False,
    }

    response = requests.post(
        f"{url}/v1/chat/completions",
        json=payload,
        timeout=300,
    )

    print("HTTP:", response.status_code)
    print(response.text)