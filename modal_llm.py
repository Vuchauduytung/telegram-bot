import subprocess
import time

import modal


# ============================================================
# Configuration
# ============================================================

APP_NAME = "cloud-bot-llm"

MODEL_NAME = "Qwen/Qwen3.6-35B-A3B-FP8"
MODEL_REVISION = "95a723d08a9490559dae23d0cff1d9466213d989"

PORT = 8000

# Keep one replica alive at all times.
MIN_CONTAINERS = 1

# One request at a time per replica for low latency.
TARGET_CONCURRENCY = 1

# H100 is enough for the ~35 GB FP8 model.
GPU = "H100"


# ============================================================
# Modal volumes
# ============================================================

HF_CACHE_PATH = "/root/.cache/huggingface"
HF_CACHE_VOL = modal.Volume.from_name(
    "cloud-bot-huggingface-cache",
    create_if_missing=True,
)

DG_CACHE_PATH = "/root/.cache/deep_gemm"
DG_CACHE_VOL = modal.Volume.from_name(
    "cloud-bot-deepgemm-cache",
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
            "SGLANG_ENABLE_JIT_DEEPGEMM": "1",
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
        "0.8",

        # Context length
        "--context-length",
        "32768",

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

    volumes={
        HF_CACHE_PATH: HF_CACHE_VOL,
        DG_CACHE_PATH: DG_CACHE_VOL,
    },

    port=PORT,

    # IMPORTANT:
    # Keep one GPU container alive.
    min_containers=MIN_CONTAINERS,

    # Keep concurrency low for chatbot latency.
    target_concurrency=TARGET_CONCURRENCY,

    # Give Qwen/SGLang enough time to initialize.
    startup_timeout=20 * 60,

    # Keep warm container alive.
    scaledown_window=30 * 60,

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