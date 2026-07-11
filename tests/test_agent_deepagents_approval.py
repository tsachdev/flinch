"""
Tests for agent_deepagents/approval.py — the checkpoint/interrupt approval
flow that replaces the execution side of the legacy pending_queue mechanism.

Uses a temp checkpoint DB per test so nothing touches the real
flinch_checkpoints.db. Restart durability is proven by resetting the
cached checkpointer/compiled-graph and reconnecting to the same DB file —
the same thing a fresh `python main.py` process does on boot.
"""
import unittest
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch


class TestApprovalFlow(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.db_path = self.tmpdir / "test_checkpoints.db"

        import agent_deepagents.checkpointer as checkpointer
        import agent_deepagents.approval as approval
        self.checkpointer = checkpointer
        self.approval = approval

        self._patcher = patch.object(checkpointer, "CHECKPOINT_DB_PATH", self.db_path)
        self._patcher.start()
        checkpointer.reset()
        approval.reset()

        self.executed = []
        approval.register_executor("test_delete", lambda payload: self._record(payload))

    def _record(self, payload):
        self.executed.append(payload)
        return {"status": "trashed", **payload}

    def tearDown(self):
        self.checkpointer.reset()
        self.approval.reset()
        self._patcher.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_start_approval_does_not_execute(self):
        tid = str(uuid.uuid4())
        result = self.approval.start_approval(tid, "test_delete", {"email_id": "a1"}, "obvious promo")
        self.assertIn("__interrupt__", result)
        self.assertEqual(self.executed, [])
        self.assertTrue(self.approval.is_pending(tid))

    def test_resume_approved_executes_underlying_tool(self):
        tid = str(uuid.uuid4())
        self.approval.start_approval(tid, "test_delete", {"email_id": "a1"}, "obvious promo")
        result = self.approval.resume_approval(tid, approved=True)
        self.assertEqual(result["status"], "trashed")
        self.assertEqual(self.executed, [{"email_id": "a1"}])
        self.assertFalse(self.approval.is_pending(tid))

    def test_resume_rejected_does_not_execute(self):
        tid = str(uuid.uuid4())
        self.approval.start_approval(tid, "test_delete", {"email_id": "a1"}, "uncertain")
        result = self.approval.resume_approval(tid, approved=False)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(self.executed, [])
        self.assertFalse(self.approval.is_pending(tid))

    def test_survives_simulated_process_restart(self):
        """Kill-and-resume: start a proposal, then simulate a fresh process
        by dropping every in-memory cache and reconnecting to the same DB
        file before resuming — proving the pending approval's state was
        actually persisted to disk, not just held in memory."""
        tid = str(uuid.uuid4())
        self.approval.start_approval(tid, "test_delete", {"email_id": "restart-me"}, "uncertain")

        # Simulate process restart: drop every cached object.
        self.checkpointer.reset()
        self.approval.reset()
        self.executed.clear()
        self.approval.register_executor("test_delete", lambda payload: self._record(payload))

        self.assertTrue(self.approval.is_pending(tid))
        result = self.approval.resume_approval(tid, approved=True)
        self.assertEqual(result["status"], "trashed")
        self.assertEqual(self.executed, [{"email_id": "restart-me"}])

    def test_unknown_task_type_reports_error_instead_of_crashing(self):
        tid = str(uuid.uuid4())
        self.approval.start_approval(tid, "no_such_executor", {"email_id": "a1"}, "reason")
        result = self.approval.resume_approval(tid, approved=True)
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
