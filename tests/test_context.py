"""
Tests for agent/context.py
Uses a temporary memory directory
"""
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile
import shutil


class TestContextBuilder(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        # Create expected directory structure
        (self.tmpdir / "roles" / "support_agent" / "summaries").mkdir(parents=True)
        (self.tmpdir / "roles" / "support_agent" / "sessions").mkdir(parents=True)
        (self.tmpdir / "shared" / "entities").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_role(self, name="support_agent"):
        return {
            "name": name,
            "persona": f"You are Flinch's {name}.",
            "tools": [],
            "registry": {},
            "skills": "",
            "max_tokens": 1024,
        }

    def _make_event(self, payload=None):
        return {
            "id": "evt-001",
            "type": "support_ticket",
            "source": "test",
            "payload": payload or {"ticket_id": "T001"},
        }

    def test_context_contains_persona(self):
        with patch("agent.context.MEMORY_DIR", self.tmpdir), \
             patch("agent.context.load_skills", return_value=""):
            from agent.context import build_context
            context = build_context(self._make_role(), self._make_event())
        self.assertIn("You are Flinch's support_agent.", context)

    def test_context_includes_summary_when_present(self):
        summary_file = self.tmpdir / "roles" / "support_agent" / "summaries"
        # Write a today-dated summary
        from datetime import datetime
        today = datetime.utcnow().strftime("%Y-%m-%d")
        (summary_file / f"{today}.md").write_text("## Today's summary\nAll quiet.")

        with patch("agent.context.MEMORY_DIR", self.tmpdir), \
             patch("agent.context.load_skills", return_value=""):
            from agent.context import build_context
            context = build_context(self._make_role(), self._make_event())
        self.assertIn("All quiet.", context)

    def test_context_falls_back_to_most_recent_summary(self):
        summary_dir = self.tmpdir / "roles" / "support_agent" / "summaries"
        (summary_dir / "2026-03-01.md").write_text("## Old summary\nOld content.")

        with patch("agent.context.MEMORY_DIR", self.tmpdir), \
             patch("agent.context.load_skills", return_value=""):
            from agent.context import build_context
            context = build_context(self._make_role(), self._make_event())
        self.assertIn("Old content.", context)

    def test_context_no_summary_still_returns_persona(self):
        with patch("agent.context.MEMORY_DIR", self.tmpdir), \
             patch("agent.context.load_skills", return_value=""):
            from agent.context import build_context
            context = build_context(self._make_role(), self._make_event())
        self.assertIn("You are Flinch's support_agent.", context)
        self.assertIsInstance(context, str)
        self.assertGreater(len(context), 0)

    def test_context_loads_customer_entity_when_customer_id_in_payload(self):
        customers_file = self.tmpdir / "shared" / "entities" / "customers.md"
        customers_file.write_text("# Known customers\n\n## Sarah — customer_id: C001\n- email: sarah@example.com")

        event = self._make_event(payload={"ticket_id": "T001", "customer_id": "C001"})
        with patch("agent.context.MEMORY_DIR", self.tmpdir), \
             patch("agent.context.load_skills", return_value=""):
            from agent.context import build_context
            context = build_context(self._make_role(), event)
        self.assertIn("sarah@example.com", context)

    def test_context_skips_entity_when_no_matching_payload_key(self):
        customers_file = self.tmpdir / "shared" / "entities" / "customers.md"
        customers_file.write_text("# Known customers\n\n## Sarah — customer_id: C001")

        # event has no customer_id in payload
        event = self._make_event(payload={"ticket_id": "T001"})
        with patch("agent.context.MEMORY_DIR", self.tmpdir), \
             patch("agent.context.load_skills", return_value=""):
            from agent.context import build_context
            context = build_context(self._make_role(), event)
        self.assertNotIn("customer_id: C001", context)

    def test_context_includes_skills_when_present(self):
        with patch("agent.context.MEMORY_DIR", self.tmpdir), \
             patch("agent.context.load_skills", return_value="## Skill: triage\nAlways triage first."):
            from agent.context import build_context
            context = build_context(self._make_role(), self._make_event())
        self.assertIn("Always triage first.", context)

    def test_context_sections_separated_by_divider(self):
        summary_dir = self.tmpdir / "roles" / "support_agent" / "summaries"
        from datetime import datetime
        today = datetime.utcnow().strftime("%Y-%m-%d")
        (summary_dir / f"{today}.md").write_text("Summary content.")

        with patch("agent.context.MEMORY_DIR", self.tmpdir), \
             patch("agent.context.load_skills", return_value="Skill content."):
            from agent.context import build_context
            context = build_context(self._make_role(), self._make_event())
        self.assertIn("---", context)


if __name__ == "__main__":
    unittest.main()
