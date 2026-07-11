"""
Tests for ui/console.py::_execute_approval — the shared helper that lets
/approve, /reject, and their bulk variants handle both legacy pending_queue
rows (no _thread_id -> direct tool call, as before) and DeepAgents-era rows
(_thread_id present -> resume the checkpointed approval graph).
"""
import unittest
from unittest.mock import patch, MagicMock

from ui.console import _execute_approval


class TestExecuteApproval(unittest.TestCase):

    def test_legacy_row_approved_calls_delete_email_directly(self):
        task = {"task_type": "delete_email", "payload": {"email_id": "abc"}}
        with patch("ui.console.delete_email", return_value={"status": "trashed"}) as mock_delete:
            result = _execute_approval(task, approved=True)
        mock_delete.assert_called_once_with("abc")
        self.assertEqual(result["status"], "trashed")

    def test_legacy_microsoft_row_approved_calls_microsoft_delete(self):
        task = {"task_type": "delete_email_microsoft", "payload": {"email_id": "xyz"}}
        with patch("roles.email_reviewer.microsoft_tools.delete_email",
                   return_value={"status": "trashed"}) as mock_delete:
            result = _execute_approval(task, approved=True)
        mock_delete.assert_called_once_with("xyz")
        self.assertEqual(result["status"], "trashed")

    def test_legacy_row_rejected_does_not_call_anything(self):
        task = {"task_type": "delete_email", "payload": {"email_id": "abc"}}
        with patch("ui.console.delete_email") as mock_delete:
            result = _execute_approval(task, approved=False)
        mock_delete.assert_not_called()
        self.assertEqual(result["status"], "rejected")

    def test_deepagents_row_resumes_checkpoint_instead_of_direct_call(self):
        task = {"task_type": "delete_email", "payload": {"email_id": "abc", "_thread_id": "tid-1"}}
        with patch("agent_deepagents.approval.resume_approval",
                   return_value={"status": "trashed"}) as mock_resume, \
             patch("ui.console.delete_email") as mock_delete:
            result = _execute_approval(task, approved=True)
        mock_resume.assert_called_once_with("tid-1", approved=True)
        mock_delete.assert_not_called()
        self.assertEqual(result["status"], "trashed")

    def test_deepagents_row_rejected_resumes_with_approved_false(self):
        task = {"task_type": "delete_email", "payload": {"email_id": "abc", "_thread_id": "tid-2"}}
        with patch("agent_deepagents.approval.resume_approval",
                   return_value={"status": "rejected"}) as mock_resume:
            result = _execute_approval(task, approved=False)
        mock_resume.assert_called_once_with("tid-2", approved=False)
        self.assertEqual(result["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
