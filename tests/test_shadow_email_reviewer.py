"""
Opt-in shadow-mode regression test — runs every committed fixture under
tests/fixtures/email_reviewer/ through scripts/shadow_compare.py and asserts
the legacy and DeepAgents email_reviewer make the same decisions.

Skipped by default: these make real LLM calls (cost + latency + occasional
provider flakiness — see NOTES.md's M2 shadow-mode results section), so
they don't run as part of the normal fast/free `pytest` suite. Opt in with:

    FLINCH_SHADOW_LIVE=1 pytest tests/test_shadow_email_reviewer.py -v

"forced_provider" defaults to anthropic — during M2 development Google's
Gemma endpoint was visibly flaky (slow, occasional ServerErrors), so this
avoids that noise by default; set FLINCH_SHADOW_PROVIDER=google to compare
against the configured production provider instead.
"""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "email_reviewer"


@unittest.skipUnless(os.environ.get("FLINCH_SHADOW_LIVE"), "opt-in: set FLINCH_SHADOW_LIVE=1 (real LLM calls)")
class TestShadowEmailReviewer(unittest.TestCase):

    def test_all_fixtures_match_legacy_decisions(self):
        import config
        from scripts.shadow_compare import compare_fixture

        provider = os.environ.get("FLINCH_SHADOW_PROVIDER", "anthropic")

        hard_mismatches = []
        with patch.dict("config.ROLE_PROVIDERS", {"email_reviewer": provider}):
            for fixture_path in sorted(FIXTURES_DIR.glob("*.json")):
                report = compare_fixture(fixture_path)
                if report["mismatches"] and not report["flexible"]:
                    hard_mismatches.append(report)

        self.assertEqual(hard_mismatches, [],
                          f"Shadow-mode decision mismatches: {hard_mismatches}")


if __name__ == "__main__":
    unittest.main()
