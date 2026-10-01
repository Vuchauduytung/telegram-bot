import unittest

from app.config import Settings
from app.llm import build_gemini_contents, build_modal_payload


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
        llm_timeout_seconds=30,
        llm_max_tokens=128,
        valkey_url="redis://localhost:6379/0",
        session_max_turns=10,
        session_ttl=3600,
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

        self.assertEqual(payload["messages"][0], {"role": "system", "content": "Be helpful."})
        self.assertEqual(payload["messages"][1]["content"], "Hello")
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])


if __name__ == "__main__":
    unittest.main()