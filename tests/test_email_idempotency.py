"""Tests for roles/email_reviewer/idempotency.py — guard against the
delete-retry loop observed 2026-07-17/18 (same email deleted 6x in one
session, each retry a paid model round-trip).
"""
import unittest
from unittest.mock import MagicMock

from roles.email_reviewer import idempotency


class TestCheckAndRecord(unittest.TestCase):

    def setUp(self):
        idempotency.reset()

    def tearDown(self):
        idempotency.reset()

    def test_first_call_runs(self):
        run = MagicMock(return_value={"status": "trashed", "email_id": "abc"})
        result = idempotency.check_and_record("delete_email", "abc", run)
        run.assert_called_once()
        self.assertEqual(result["status"], "trashed")

    def test_duplicate_skipped_with_note(self):
        run = MagicMock(return_value={"status": "trashed", "email_id": "abc"})
        idempotency.check_and_record("delete_email", "abc", run)
        result = idempotency.check_and_record("delete_email", "abc", run)
        run.assert_called_once()  # not called again
        self.assertEqual(result["status"], "trashed")
        self.assertIn("duplicate", result["note"])

    def test_six_deletes_hit_backend_once(self):
        """The exact Jul 17-18 failure shape."""
        run = MagicMock(return_value={"status": "trashed", "email_id": "19f721631633f00e"})
        for _ in range(6):
            idempotency.check_and_record("delete_email", "19f721631633f00e", run)
        run.assert_called_once()

    def test_different_actions_independent(self):
        idempotency.check_and_record("mark_read", "abc", lambda: {"status": "marked_read"})
        run = MagicMock(return_value={"status": "trashed"})
        idempotency.check_and_record("delete_email", "abc", run)
        run.assert_called_once()

    def test_error_results_not_recorded(self):
        idempotency.check_and_record("delete_email", "abc", lambda: {"error": "500"})
        run = MagicMock(return_value={"status": "trashed"})
        result = idempotency.check_and_record("delete_email", "abc", run)
        run.assert_called_once()  # retry after failure is allowed
        self.assertEqual(result["status"], "trashed")

    def test_exceptions_propagate_and_not_recorded(self):
        def boom():
            raise RuntimeError("api down")
        with self.assertRaises(RuntimeError):
            idempotency.check_and_record("delete_email", "abc", boom)
        run = MagicMock(return_value={"status": "trashed"})
        idempotency.check_and_record("delete_email", "abc", run)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
