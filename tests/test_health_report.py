"""Tests for memory/health.py — the daily health block appended to the
Flinch digest. Parses a synthetic journal so it needs no journalctl.
"""
import unittest

from memory.health import health_report

CLEAN_DAY = """
Jul 19 19:37:39 gen-claw python3[1]:   [llm] provider: deepseek, model: deepseek-v4-flash
Jul 19 19:37:42 gen-claw python3[1]:   [gmail] fetched 10 unread emails
Jul 19 19:38:06 gen-claw python3[1]:   [gmail] trashed → 19b516afd643c36f
Jul 19 19:38:06 gen-claw python3[1]:   [gmail] trashed → 19ae56367105c549
Jul 19 19:38:07 gen-claw python3[1]:   [llm] provider: deepseek, model: deepseek-v4-flash
Jul 19 19:38:20 gen-claw python3[1]: [queue] completed → f06be9b4
"""

BAD_DAY = """
Jul 18 10:00:00 gen-claw python3[1]:   [llm] provider: nvidia, model: nvidia-nemotron-3-super-120b
Jul 18 10:00:02 gen-claw python3[1]:   [llm] nvidia failed (RateLimitError) — falling back to anthropic
Jul 18 10:00:02 gen-claw python3[1]:   [llm] provider: anthropic, model: claude-haiku-4-5-20251001
Jul 18 10:00:05 gen-claw python3[1]:   [fallback-alert] alert email sent → tushar.sachdev@gmail.com
Jul 18 10:00:06 gen-claw python3[1]:   [gmail] fetched 10 unread emails
Jul 18 10:00:07 gen-claw python3[1]:   [session-guard] delete_email hit per-session limit (15) — refusing
Jul 18 10:00:08 gen-claw python3[1]:   [gmail] trashed → aaa
Jul 18 10:02:56 gen-claw python3[1]: [memory] console summary failed: Error code: 400 credit balance too low
"""


class TestHealthReport(unittest.TestCase):

    def test_clean_day_reports_no_flags(self):
        r = health_report("2026-07-19", journal=CLEAN_DAY)
        self.assertIn("deepseek 2", r)
        self.assertIn("Runs completed: 1", r)
        self.assertIn("trashed: 2", r)
        self.assertIn("Flags: none — all clean", r)

    def test_bad_day_flags_fallback_alert_cap_and_error(self):
        r = health_report("2026-07-18", journal=BAD_DAY)
        self.assertIn("1 provider fallback(s)", r)
        self.assertIn("alert email(s) sent", r)
        self.assertIn("per-session cap hit 1x", r)
        self.assertIn("error line(s)", r)
        self.assertNotIn("none — all clean", r)

    def test_no_journal_is_graceful(self):
        r = health_report("2026-07-19", journal="")
        self.assertIn("no journal available", r)

    def test_provider_breakdown_counts_each(self):
        r = health_report("2026-07-18", journal=BAD_DAY)
        self.assertIn("nvidia 1", r)
        self.assertIn("anthropic 1", r)


if __name__ == "__main__":
    unittest.main()
