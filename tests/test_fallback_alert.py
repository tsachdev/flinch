"""Tests for agent/fallback_alert.py — the consecutive-fallback alerter
added after the Jul 17-19 2026 incident (primary provider rate-limited on
every call; silent fallback billed the Anthropic key for 3 days).
"""
import unittest
from unittest.mock import patch

from agent import fallback_alert


def _reset():
    fallback_alert._consecutive = 0
    fallback_alert._last_alert_ts = 0.0


class TestFallbackAlert(unittest.TestCase):

    def setUp(self):
        _reset()

    def tearDown(self):
        _reset()

    @patch("agent.fallback_alert._send_alert")
    def test_no_alert_below_threshold(self, mock_send):
        with patch("agent.fallback_alert._threshold", return_value=5):
            for _ in range(4):
                fallback_alert.record_fallback("nvidia", "anthropic", RuntimeError("boom"))
        mock_send.assert_not_called()

    @patch("agent.fallback_alert._send_alert")
    def test_alert_at_threshold(self, mock_send):
        with patch("agent.fallback_alert._threshold", return_value=5):
            for _ in range(5):
                fallback_alert.record_fallback("nvidia", "anthropic", RuntimeError("boom"))
        mock_send.assert_called_once()
        streak, primary, fallback, _err = mock_send.call_args[0]
        self.assertEqual((streak, primary, fallback), (5, "nvidia", "anthropic"))

    @patch("agent.fallback_alert._send_alert")
    def test_cooldown_suppresses_repeat_alerts(self, mock_send):
        with patch("agent.fallback_alert._threshold", return_value=2):
            for _ in range(10):
                fallback_alert.record_fallback("nvidia", "anthropic", RuntimeError("boom"))
        mock_send.assert_called_once()  # 9 post-threshold calls, 1 email

    @patch("agent.fallback_alert._send_alert")
    def test_success_resets_streak(self, mock_send):
        with patch("agent.fallback_alert._threshold", return_value=3):
            for _ in range(2):
                fallback_alert.record_fallback("nvidia", "anthropic", RuntimeError("boom"))
            fallback_alert.record_success("nvidia")
            for _ in range(2):
                fallback_alert.record_fallback("nvidia", "anthropic", RuntimeError("boom"))
        mock_send.assert_not_called()

    @patch("agent.fallback_alert._send_alert", side_effect=RuntimeError("gmail down"))
    def test_send_failure_never_raises(self, mock_send):
        with patch("agent.fallback_alert._threshold", return_value=1):
            fallback_alert.record_fallback("nvidia", "anthropic", RuntimeError("boom"))
        # reaching here without an exception is the assertion


class TestLegacyLlmIntegration(unittest.TestCase):
    """agent/llm.py should record fallbacks/successes with the alerter."""

    def setUp(self):
        _reset()

    @patch("agent.fallback_alert.record_fallback")
    @patch("agent.providers.nvidia.chat")
    @patch("agent.providers.anthropic.chat")
    def test_chat_records_fallback(self, mock_anthropic, mock_nvidia, mock_record):
        from unittest.mock import MagicMock
        from agent import llm

        with patch.dict("config.ROLE_PROVIDERS", {"test_role": "nvidia"}), \
             patch.dict("config.ROLE_PROVIDER_FALLBACK", {"nvidia": "anthropic"}):
            mock_nvidia.side_effect = TimeoutError("rate limited")
            mock_anthropic.return_value = {"stop_reason": "end_turn", "content": [], "raw": [], "tokens": 1}
            with patch("agent.providers.nvidia.create_client", return_value=MagicMock()), \
                 patch("agent.providers.anthropic.create_client", return_value=MagicMock()):
                llm.chat({"name": "test_role"}, "sys", [{"role": "user", "content": "hi"}], [])

        mock_record.assert_called_once()
        primary, fallback, err = mock_record.call_args[0]
        self.assertEqual((primary, fallback), ("nvidia", "anthropic"))
        self.assertIsInstance(err, TimeoutError)


if __name__ == "__main__":
    unittest.main()
