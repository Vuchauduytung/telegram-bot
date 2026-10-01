import unittest

from app.config import Settings
from app.llm import build_gemini_contents, build_modal_headers, build_modal_payload


def settings(provider: str) -> Settings:
    return Settings(
        bot_token="test-token",
        llm_provider=provider,
        system_prompt="Be helpful.",
        gemini_model="gemini-2.5-flash",
        google_cloud_project="test-project",
        google_cloud_location="global",
        modal_llm_url="https://example.modal.run",
        modal_llm_model="test-model",
        modal_proxy_token_id="wk-test-id",
        modal_proxy_token_secret="ws-test-secret",
        llm_timeout_seconds=30,
        llm_max_tokens=128,
        valkey_url="redis://localhost:6379/0",
        session_max_turns=10,
        session_ttl=3600,
        knowledge_dir="knowledge",
        qdrant_url="http://localhost:6333",
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


if __name__ == "__main__":
    unittest.main()