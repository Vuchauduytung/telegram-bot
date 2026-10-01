import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from app.config import Settings, get_settings
from app.llm import (
    _post_modal_completion,
    build_gemini_contents,
    build_modal_headers,
    build_modal_payload,
)


def settings(provider: str) -> Settings:
    return Settings(
        bot_token="test-token",
        llm_provider=provider,
        system_prompt="Be helpful.",
        gemini_api_key="test-api-key",
        gemini_model="gemini-2.5-flash",
        google_cloud_project="test-project",
        google_cloud_location="global",
        modal_llm_url="https://example.modal.run",
        modal_llm_model="test-model",
        modal_proxy_token_id="wk-test-id",
        modal_proxy_token_secret="ws-test-secret",
        modal_max_requests_per_month=400,
        embedding_provider="local",
        llm_timeout_seconds=30,
        llm_max_tokens=128,
        valkey_url="redis://localhost:6379/0",
        valkey_token="",
        session_max_turns=10,
        session_ttl=3600,
        knowledge_dir="knowledge",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="",
        qdrant_collection="cloud_bot_knowledge",
        embedding_model="gemini-embedding-001",
        embedding_dimensions=768,
        chunk_size=1200,
        chunk_overlap=160,
        rag_top_k=5,
        rag_min_score=0.35,
        rag_context_max_chars=10000,
    )


class LLMFormattingTests(unittest.TestCase):
    def test_template_environment_names_configure_hosted_services(self):
        template_env = {
            "TELEGRAM_BOT_TOKEN": "telegram-test-token",
            "LLM_PROVIDER": "modal",
            "MODAL_ENDPOINT_URL": "https://private.modal.run/",
            "MODAL_PROXY_TOKEN": "wk-test-key.ws-test-secret",
            "QDRANT_URL": "https://qdrant.example:6333",
            "QDRANT_API_KEY": "qdrant-test-key",
            "VALKEY_URL": "rediss://valkey.example:6379",
            "VALKEY_TOKEN": "valkey-test-token",
        }
        with patch.dict(os.environ, template_env, clear=True):
            loaded = get_settings()

        self.assertEqual(loaded.bot_token, "telegram-test-token")
        self.assertEqual(loaded.modal_llm_url, "https://private.modal.run")
        self.assertEqual(loaded.modal_proxy_token_id, "wk-test-key")
        self.assertEqual(loaded.modal_proxy_token_secret, "ws-test-secret")
        self.assertEqual(loaded.qdrant_url, "https://qdrant.example:6333")
        self.assertEqual(loaded.qdrant_api_key, "qdrant-test-key")
        self.assertEqual(loaded.valkey_url, "rediss://valkey.example:6379")
        self.assertEqual(loaded.valkey_token, "valkey-test-token")

    def test_gemini_maps_assistant_history_to_model_role(self):
        contents = build_gemini_contents(
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
                {"role": "user", "content": "Again"},
            ]
        )

        self.assertEqual([item.role for item in contents], ["user", "model", "user"])
        self.assertEqual(contents[1].parts[0].text, "Hi")

    def test_modal_payload_includes_system_prompt_and_chat_history(self):
        payload = build_modal_payload(
            settings("modal"),
            [{"role": "user", "content": "Hello"}],
        )

        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertTrue(payload["messages"][0]["content"].startswith("Be helpful."))
        self.assertEqual(payload["messages"][1]["content"], "Hello")
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])

    def test_modal_headers_use_proxy_token_pair(self):
        self.assertEqual(
            build_modal_headers(settings("modal")),
            {"Modal-Key": "wk-test-id", "Modal-Secret": "ws-test-secret"},
        )

    def test_modal_prompt_includes_rag_context_and_source_policy(self):
        payload = build_modal_payload(
            settings("modal"),
            [{"role": "user", "content": "Question"}],
            "[1] Guide (guide.md)\nThe answer is 42.",
        )

        prompt = payload["messages"][0]["content"]
        self.assertIn("The answer is 42.", prompt)
        self.assertIn("Cite only source numbers", prompt)

    def test_modal_prompt_is_transparent_when_retrieval_has_no_context(self):
        payload = build_modal_payload(settings("modal"), [{"role": "user", "content": "Question"}])

        self.assertIn("document-specific question", payload["messages"][0]["content"])
        self.assertNotIn("REFERENCE MATERIAL", payload["messages"][0]["content"])

    def test_modal_completion_retries_startup_503_once(self):
        request = httpx.Request("POST", "https://example.modal.run/v1/chat/completions")
        unavailable = httpx.Response(503, request=request)
        ready = httpx.Response(200, json={"ok": True}, request=request)
        client = Mock()
        client.post = AsyncMock(side_effect=[unavailable, ready])

        async def check_retry():
            with patch("app.llm.asyncio.sleep", new_callable=AsyncMock) as sleep:
                response = await _post_modal_completion(client, str(request.url), {}, {})
                sleep.assert_awaited_once_with(1)
            self.assertEqual(response.json(), {"ok": True})

        import asyncio

        asyncio.run(check_retry())

    def test_free_tier_gemini_api_client_uses_api_key(self):
        from unittest.mock import patch

        sentinel = object()
        with patch("google.genai.Client", return_value=sentinel) as client_factory:
            from app.llm import _gemini_api_client

            _gemini_api_client.cache_clear()
            self.assertIs(_gemini_api_client("test-api-key"), sentinel)
            client_factory.assert_called_once_with(api_key="test-api-key")
            _gemini_api_client.cache_clear()


if __name__ == "__main__":
    unittest.main()