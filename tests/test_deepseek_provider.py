"""DeepSeek provider wiring — both the legacy (agent/llm.py) and deepagents
(agent_deepagents/providers.py) paths must resolve provider 'deepseek' to
deepseek-v4-flash on the OpenAI-compatible DeepSeek endpoint.
"""
import unittest
from unittest.mock import patch, MagicMock


class TestDeepSeekDeepAgents(unittest.TestCase):

    def test_default_model_resolves(self):
        from agent_deepagents import providers
        with patch("config.DEEPSEEK_MODEL", "deepseek-v4-flash", create=True):
            self.assertEqual(providers._default_model("deepseek"), "deepseek-v4-flash")

    def test_init_chat_model_uses_deepseek_endpoint(self):
        from agent_deepagents import providers
        captured = {}

        def fake_chat_openai(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        with patch("config.DEEPSEEK_API_KEY", "sk-test", create=True), \
             patch("config.DEEPSEEK_BASE_URL", "https://api.deepseek.com", create=True), \
             patch("langchain_openai.ChatOpenAI", side_effect=fake_chat_openai):
            providers._init_chat_model("deepseek", "deepseek-v4-flash", 1024)

        self.assertEqual(captured["base_url"], "https://api.deepseek.com")
        self.assertEqual(captured["model"], "deepseek-v4-flash")

    def test_deepseek_primary_falls_back_to_anthropic(self):
        from agent_deepagents import providers
        primary = MagicMock()
        fallback = MagicMock()

        def fake_init(provider, model, max_tokens):
            return primary if provider == "deepseek" else fallback

        with patch.dict("agent_deepagents.providers.ROLE_PROVIDERS",
                        {"default": "deepseek", "email_reviewer": "deepseek"}, clear=True), \
             patch.dict("agent_deepagents.providers.ROLE_PROVIDER_FALLBACK",
                        {"deepseek": "anthropic"}, clear=True), \
             patch("agent_deepagents.providers._init_chat_model", side_effect=fake_init):
            _model, middleware = providers.get_model_and_middleware({"name": "email_reviewer"})

        # fallback middleware present, named correctly
        fb = [m for m in middleware if isinstance(m, providers.ProviderFallbackMiddleware)]
        self.assertEqual(len(fb), 1)
        self.assertEqual(fb[0].primary_name, "deepseek")
        self.assertEqual(fb[0].fallback_name, "anthropic")


class TestDeepSeekLegacy(unittest.TestCase):

    def test_default_model_resolves(self):
        from agent import llm
        with patch("config.DEEPSEEK_MODEL", "deepseek-v4-flash", create=True):
            self.assertEqual(llm._default_model("deepseek"), "deepseek-v4-flash")

    def test_call_routes_to_deepseek_provider(self):
        from agent import llm
        with patch.dict("config.ROLE_PROVIDERS", {"test_role": "deepseek"}), \
             patch.dict("config.ROLE_PROVIDER_FALLBACK", {"deepseek": "anthropic"}), \
             patch("config.DEEPSEEK_MODEL", "deepseek-v4-flash", create=True):
            with patch("agent.providers.deepseek.create_client", return_value=MagicMock()), \
                 patch("agent.providers.deepseek.chat",
                       return_value={"stop_reason": "end_turn", "content": [], "raw": [], "tokens": 1}) as mock_chat:
                result = llm.chat({"name": "test_role"}, "sys",
                                  [{"role": "user", "content": "hi"}], [])
        mock_chat.assert_called_once()
        self.assertEqual(result["tokens"], 1)


if __name__ == "__main__":
    unittest.main()
