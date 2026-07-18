"""Tests for agent_deepagents/graduation.py — the leveled Graduation Ledger
gate (execution-layer M3) that replaces the binary approval gate on a DEV
instance (GRADUATION_PACK env var; production never sets it).

Everything is isolated: temp ledger JSONL, temp checkpoint DB, temp
eventqueue DB (never flinch.db), and patched TOOL_REGISTRY entries so no
Gmail call can happen. Requires `pip install -e ~/execution-layer` in this
venv, which is the dev-instance setup this feature assumes.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

EXECUTION_LAYER = Path.home() / "execution-layer"
PACK = EXECUTION_LAYER / "packs" / "email-triage"


class TestGraduationGate(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self._env = patch.dict(os.environ, {
            "GRADUATION_PACK": str(PACK),
            "GRADUATION_LEDGER": str(self.tmpdir / "ledger.jsonl"),
            "GRADUATION_CHECKPOINT_DB": str(self.tmpdir / "checkpoints.db"),
        })
        self._env.start()

        import eventqueue.bus as bus
        self.bus = bus
        self._db = patch.object(bus, "DB_PATH", self.tmpdir / "flinch_test.db")
        self._db.start()

        from roles.email_reviewer import tools as gmail_tools
        self.executed = []

        def fake_delete(email_id):
            self.executed.append(("delete_email", email_id))
            return {"status": "trashed", "email_id": email_id}

        def fake_mark_read(email_id):
            self.executed.append(("mark_read", email_id))
            return {"status": "read", "email_id": email_id}

        self._registry = patch.dict(gmail_tools.TOOL_REGISTRY, {
            "delete_email": fake_delete,
            "mark_read": fake_mark_read,
        })
        self._registry.start()

        from agent_deepagents import graduation
        self.graduation = graduation
        graduation.reset()

    def tearDown(self):
        self.graduation.reset()
        self._registry.stop()
        self._db.stop()
        self._env.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _wrapped_tools(self):
        from agent.registry import get_role
        from agent_deepagents.tools import wrap_tool_registry
        role = get_role("cron")
        wrapped = wrap_tool_registry(role["tools"], role["registry"])
        return role, wrapped, self.graduation.wrap_gated_tools(wrapped, role, "cron")

    def _tool(self, tools, name):
        return next(t for t in tools if t.name == name)

    def test_l0_delete_queues_and_mirrors_to_console_queue(self):
        _, _, gated = self._wrapped_tools()
        result = self._tool(gated, "delete_email").func(email_id="x1")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(self.executed, [])

        rows = self.bus.get_pending_tasks()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["payload"]["email_id"], "x1")
        self.assertIn("_gl_thread_id", rows[0]["payload"])
        self.assertEqual(len(self.graduation.get_adapter().pending()), 1)

    def test_console_resume_path_executes_on_approve(self):
        _, _, gated = self._wrapped_tools()
        self._tool(gated, "delete_email").func(email_id="x2")
        row = self.bus.get_pending_tasks()[0]

        outcome = self.graduation.resume(
            row["payload"]["_gl_thread_id"], approved=True)
        self.assertEqual(outcome["result"]["status"], "trashed")
        self.assertEqual(self.executed, [("delete_email", "x2")])
        self.assertEqual(self.graduation.get_adapter().pending(), [])

        history = self.graduation.get_adapter().ledger.history("delete_email")
        self.assertEqual(history[-1]["metrics"], {"approval_rate": True})

    def test_reject_keeps_the_email(self):
        _, _, gated = self._wrapped_tools()
        self._tool(gated, "delete_email").func(email_id="x3")
        row = self.bus.get_pending_tasks()[0]
        outcome = self.graduation.resume(
            row["payload"]["_gl_thread_id"], approved=False, reason="keep it")
        self.assertEqual(outcome["result"]["status"], "rejected")
        self.assertEqual(self.executed, [])

    def test_ungoverned_tools_pass_through_untouched(self):
        _, before, gated = self._wrapped_tools()
        untouched = self._tool(before, "get_unread_emails")
        self.assertIs(self._tool(gated, "get_unread_emails"), untouched)
        self.assertIsNot(self._tool(gated, "delete_email"),
                         self._tool(before, "delete_email"))

    def test_l3_is_passthrough_with_unchanged_behavior(self):
        """The M3 parity requirement: a graduated action behaves exactly like
        the ungated role, executing directly and silently."""
        lines = [json.dumps({
            "type": "promotion", "action": "delete_email", "from": frm,
            "to": to, "rule": f"{frm}_to_{to}", "mode": "auto",
            "pack": "email-triage", "ts": "2026-07-14T00:00:00+00:00",
        }) for frm, to in [("L0", "L1"), ("L1", "L2"), ("L2", "L3")]]
        Path(os.environ["GRADUATION_LEDGER"]).write_text("\n".join(lines) + "\n")
        self.graduation.reset()

        _, _, gated = self._wrapped_tools()
        result = self._tool(gated, "delete_email").func(email_id="x4")
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["result"]["status"], "trashed")
        self.assertEqual(self.executed, [("delete_email", "x4")])
        self.assertEqual(self.bus.get_pending_tasks(), [])

    def test_console_api_status_shape(self):
        self.graduation.get_adapter()
        payload = self.graduation.status()
        self.assertEqual(payload["pack"], "email-triage")
        self.assertIn("delete_email", payload["actions"])
        self.assertEqual(payload["actions"]["delete_email"]["level"], "L0")
        self.assertEqual(payload["advisories"], [])


if __name__ == "__main__":
    unittest.main()
