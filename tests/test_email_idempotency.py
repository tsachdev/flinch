"""Tests for roles/email_reviewer/idempotency.py — guard against the
delete-retry loop observed 2026-07-17/18 (same email deleted 6x in one
session, each retry a paid model round-trip).
"""
import unittest
from unittest.mock import MagicMock, patch

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


class TestSessionCaps(unittest.TestCase):
    """Per-run action caps — the 2026-07-19 runaway defense."""

    def setUp(self):
        idempotency.reset_session()

    def tearDown(self):
        idempotency.reset_session()

    def test_fetch_cap_stops_the_purge_loop(self):
        run = MagicMock(return_value={"emails": []})
        with patch("config.EMAIL_MAX_FETCHES_PER_SESSION", 3, create=True):
            results = [idempotency.guard("get_unread_emails", run) for _ in range(6)]
        self.assertEqual(run.call_count, 3)  # capped
        self.assertEqual(results[-1]["status"], "limit_reached")

    def test_delete_cap_bounds_one_session(self):
        with patch("config.EMAIL_MAX_DELETES_PER_SESSION", 15, create=True):
            for i in range(30):
                idempotency.check_and_record(
                    "delete_email", f"id{i}",
                    lambda: {"status": "trashed"})
        # 77-email runaway becomes at most 15 per run
        self.assertEqual(idempotency._counts["delete_email"], 15)

    def test_reset_clears_counts_between_sessions(self):
        with patch("config.EMAIL_MAX_DELETES_PER_SESSION", 2, create=True):
            for i in range(5):
                idempotency.check_and_record("delete_email", f"a{i}", lambda: {"status": "trashed"})
            self.assertEqual(idempotency._counts["delete_email"], 2)
            idempotency.reset_session()
            r = idempotency.check_and_record("delete_email", "b0", lambda: {"status": "trashed"})
            self.assertEqual(r["status"], "trashed")

    def test_limit_reached_does_not_run_action(self):
        run = MagicMock(return_value={"status": "trashed"})
        with patch("config.EMAIL_MAX_DELETES_PER_SESSION", 1, create=True):
            idempotency.check_and_record("delete_email", "x", run)
            idempotency.check_and_record("delete_email", "y", run)
        run.assert_called_once()  # second never executed the real delete


if __name__ == "__main__":
    unittest.main()
