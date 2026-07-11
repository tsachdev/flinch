"""
Opt-in shadow-mode regression test — runs every committed fixture for every
role through scripts/shadow_compare.py and asserts the legacy and
DeepAgents agent loops make the same decisions.

Skipped by default: these make real LLM calls (cost + latency + occasional
provider flakiness — see NOTES.md's M2 shadow-mode results section), so
they don't run as part of the normal fast/free `pytest` suite. Opt in with:

    FLINCH_SHADOW_LIVE=1 pytest tests/test_shadow_email_reviewer.py -v

FLINCH_SHADOW_PROVIDER defaults to anthropic for email_reviewer/
market_watcher — during M2 development Google's Gemma endpoint was visibly
flaky (slow, occasional ServerErrors) — set FLINCH_SHADOW_PROVIDER=google
to compare against the configured production provider instead.
"""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.shadow_compare import ROLE_COMPARATORS, FIXTURES_ROOT


@unittest.skipUnless(os.environ.get("FLINCH_SHADOW_LIVE"), "opt-in: set FLINCH_SHADOW_LIVE=1 (real LLM calls)")
class TestShadowModeAllRoles(unittest.TestCase):

    def test_all_fixtures_match_legacy_decisions(self):
        provider = os.environ.get("FLINCH_SHADOW_PROVIDER", "anthropic")

        hard_mismatches = []
        with patch.dict("config.ROLE_PROVIDERS",
                        {"email_reviewer": provider, "market_watcher": provider}):
            for role, comparator in ROLE_COMPARATORS.items():
                fixtures_dir = FIXTURES_ROOT / role
                if not fixtures_dir.exists():
                    continue
                for fixture_path in sorted(fixtures_dir.glob("*.json")):
                    report = comparator(fixture_path)
                    if report["mismatches"] and not report["flexible"]:
                        hard_mismatches.append((role, report))

        self.assertEqual(hard_mismatches, [],
                          f"Shadow-mode decision mismatches: {hard_mismatches}")


if __name__ == "__main__":
    unittest.main()
