"""
Side-by-side fallback tests: legacy agent/llm.py vs agent_deepagents/providers.py.

Both must make the same fallback decision for the same simulated failure:
- primary provider raises -> if a fallback is configured, the fallback provider
  is used; if not (e.g. anthropic has no configured fallback), the exception
  propagates.
"""
import unittest
from unittest.mock import patch, MagicMock

from langchain_core.runnables import RunnableLambda


class TestLegacyFallback(unittest.TestCase):
    """agent/llm.py::chat — bare `except Exception` around the primary call."""

    def _role(self, name="market_watcher"):
        return {"name": name}

    @patch("agent.providers.google.chat")
    @patch("agent.providers.anthropic.chat")
    def test_falls_back_on_primary_exception(self, mock_anthropic_chat, mock_google_chat):
        from agent import llm

        with patch.dict("config.ROLE_PROVIDERS", {"default": "anthropic", "test_role": "anthropic"}), \
             patch.dict("config.ROLE_PROVIDER_FALLBACK", {"anthropic": "google"}):
            mock_anthropic_chat.side_effect = TimeoutError("boom")
            mock_google_chat.return_value = {"stop_reason": "end_turn", "content": [], "raw": [], "tokens": 1}

            with patch("agent.providers.anthropic.create_client", return_value=MagicMock()), \
                 patch("agent.providers.google.create_client", return_value=MagicMock()):
                result = llm.chat(self._role("test_role"), "sys", [{"role": "user", "content": "hi"}], [])

        mock_anthropic_chat.assert_called_once()
        mock_google_chat.assert_called_once()
        self.assertEqual(result["tokens"], 1)

    @patch("agent.providers.anthropic.chat")
    def test_no_fallback_reraises(self, mock_anthropic_chat):
        from agent import llm

        with patch.dict("config.ROLE_PROVIDERS", {"default": "anthropic", "test_role": "anthropic"}), \
             patch.dict("config.ROLE_PROVIDER_FALLBACK", {"anthropic": None}):
            mock_anthropic_chat.side_effect = TimeoutError("boom")
            with patch("agent.providers.anthropic.create_client", return_value=MagicMock()):
                with self.assertRaises(TimeoutError):
                    llm.chat(self._role("test_role"), "sys", [{"role": "user", "content": "hi"}], [])


class TestDeepAgentsFallback(unittest.TestCase):
    """agent_deepagents/providers.py::get_model — LangChain .with_fallbacks()."""

    def _fake_model(self, name, should_raise=False):
        def _run(x):
            if should_raise:
                raise TimeoutError(f"{name} boom")
            return f"{name}-ok"
        return RunnableLambda(_run)

    def test_falls_back_on_primary_exception(self):
        from agent_deepagents import providers

        primary  = self._fake_model("anthropic", should_raise=True)
        fallback = self._fake_model("google", should_raise=False)

        def fake_init(provider, model, max_tokens):
            return primary if provider == "anthropic" else fallback

        with patch.dict("agent_deepagents.providers.ROLE_PROVIDERS",
                        {"default": "anthropic", "test_role": "anthropic"}, clear=True), \
             patch.dict("agent_deepagents.providers.ROLE_PROVIDER_FALLBACK",
                        {"anthropic": "google"}, clear=True), \
             patch("agent_deepagents.providers._init_chat_model", side_effect=fake_init):
            model = providers.get_model({"name": "test_role"})
            result = model.invoke("hi")

        self.assertEqual(result, "google-ok")

    def test_no_fallback_reraises(self):
        from agent_deepagents import providers

        primary = self._fake_model("anthropic", should_raise=True)

        def fake_init(provider, model, max_tokens):
            return primary

        with patch.dict("agent_deepagents.providers.ROLE_PROVIDERS",
                        {"default": "anthropic", "test_role": "anthropic"}, clear=True), \
             patch.dict("agent_deepagents.providers.ROLE_PROVIDER_FALLBACK",
                        {"anthropic": None}, clear=True), \
             patch("agent_deepagents.providers._init_chat_model", side_effect=fake_init):
            model = providers.get_model({"name": "test_role"})
            with self.assertRaises(TimeoutError):
                model.invoke("hi")


class TestParity(unittest.TestCase):
    """Same config, same failure -> same fallback decision, both implementations."""

    def test_google_primary_falls_back_to_anthropic_both_implementations(self):
        from agent import llm
        from agent_deepagents import providers

        # Legacy
        with patch.dict("config.ROLE_PROVIDERS", {"default": "anthropic", "test_role": "google"}), \
             patch.dict("config.ROLE_PROVIDER_FALLBACK", {"google": "anthropic"}), \
             patch("agent.providers.google.chat", side_effect=RuntimeError("rate limited")), \
             patch("agent.providers.anthropic.chat",
                   return_value={"stop_reason": "end_turn", "content": [], "raw": [], "tokens": 7}), \
             patch("agent.providers.google.create_client", return_value=MagicMock()), \
             patch("agent.providers.anthropic.create_client", return_value=MagicMock()):
            legacy_result = llm.chat({"name": "test_role"}, "sys", [{"role": "user", "content": "hi"}], [])

        # DeepAgents
        def _raise_rate_limited(_):
            raise RuntimeError("rate limited")

        anthropic_fake = RunnableLambda(lambda x: "anthropic-ok")
        google_fake     = RunnableLambda(_raise_rate_limited)

        def fake_init(provider, model, max_tokens):
            return google_fake if provider == "google" else anthropic_fake

        with patch.dict("agent_deepagents.providers.ROLE_PROVIDERS",
                        {"default": "anthropic", "test_role": "google"}, clear=True), \
             patch.dict("agent_deepagents.providers.ROLE_PROVIDER_FALLBACK",
                        {"google": "anthropic"}, clear=True), \
             patch("agent_deepagents.providers._init_chat_model", side_effect=fake_init):
            model = providers.get_model({"name": "test_role"})
            new_result = model.invoke("hi")

        # Both ended up on the anthropic fallback for the same scenario.
        self.assertEqual(legacy_result["tokens"], 7)
        self.assertEqual(new_result, "anthropic-ok")


if __name__ == "__main__":
    unittest.main()
