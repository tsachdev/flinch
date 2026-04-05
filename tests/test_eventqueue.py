"""
Tests for eventqueue/bus.py
Uses an in-memory SQLite database — never touches flinch.db
"""
import json
import sqlite3
import unittest
from unittest.mock import patch
from pathlib import Path

# Patch DB_PATH before importing bus so tests use a temp DB
TEST_DB = Path("/tmp/flinch_test.db")


def _reset_db():
    if TEST_DB.exists():
        TEST_DB.unlink()


class TestEventQueue(unittest.TestCase):

    def setUp(self):
        _reset_db()
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import init_queue
            init_queue()

    def tearDown(self):
        _reset_db()

    def test_enqueue_returns_id(self):
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import enqueue
            event_id = enqueue("support_ticket", "test", {"ticket_id": "T001"})
        self.assertIsInstance(event_id, str)
        self.assertEqual(len(event_id), 36)  # UUID4 format

    def test_enqueue_dequeue_roundtrip(self):
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import enqueue, dequeue
            event_id = enqueue("support_ticket", "test", {"ticket_id": "T001"})
            event = dequeue()
        self.assertIsNotNone(event)
        self.assertEqual(event["id"], event_id)
        self.assertEqual(event["type"], "support_ticket")
        self.assertEqual(event["source"], "test")
        self.assertEqual(event["payload"]["ticket_id"], "T001")

    def test_dequeue_sets_in_progress(self):
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import enqueue, dequeue
            event_id = enqueue("support_ticket", "test", {"ticket_id": "T001"})
            dequeue()
            conn = sqlite3.connect(TEST_DB)
            row = conn.execute(
                "SELECT status FROM queue WHERE id = ?", (event_id,)
            ).fetchone()
            conn.close()
        self.assertEqual(row[0], "in-progress")

    def test_dequeue_empty_queue_returns_none(self):
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import dequeue
            result = dequeue()
        self.assertIsNone(result)

    def test_complete_updates_status(self):
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import enqueue, dequeue, complete
            event_id = enqueue("support_ticket", "test", {"ticket_id": "T001"})
            dequeue()
            complete(event_id)
            conn = sqlite3.connect(TEST_DB)
            row = conn.execute(
                "SELECT status FROM queue WHERE id = ?", (event_id,)
            ).fetchone()
            conn.close()
        self.assertEqual(row[0], "completed")

    def test_fail_updates_status(self):
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import enqueue, dequeue, fail
            event_id = enqueue("support_ticket", "test", {"ticket_id": "T001"})
            dequeue()
            fail(event_id)
            conn = sqlite3.connect(TEST_DB)
            row = conn.execute(
                "SELECT status FROM queue WHERE id = ?", (event_id,)
            ).fetchone()
            conn.close()
        self.assertEqual(row[0], "failed")

    def test_dequeue_fifo_order(self):
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import enqueue, dequeue
            id1 = enqueue("support_ticket", "test", {"order": 1})
            id2 = enqueue("support_ticket", "test", {"order": 2})
            first = dequeue()
            second = dequeue()
        self.assertEqual(first["id"], id1)
        self.assertEqual(second["id"], id2)

    def test_payload_serialisation(self):
        payload = {"nested": {"key": "value"}, "list": [1, 2, 3], "number": 42}
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import enqueue, dequeue
            enqueue("test_event", "test", payload)
            event = dequeue()
        self.assertEqual(event["payload"], payload)

    def test_enqueue_pending(self):
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import enqueue_pending, get_pending_tasks
            task_id = enqueue_pending(
                "delete_email",
                {"email_id": "abc123"},
                "Promotional email"
            )
            tasks = get_pending_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], task_id)
        self.assertEqual(tasks[0]["task_type"], "delete_email")
        self.assertEqual(tasks[0]["payload"]["email_id"], "abc123")
        self.assertEqual(tasks[0]["reason"], "Promotional email")

    def test_update_pending_status(self):
        with patch("eventqueue.bus.DB_PATH", TEST_DB):
            from eventqueue.bus import enqueue_pending, update_pending_status, get_pending_tasks
            task_id = enqueue_pending("delete_email", {"email_id": "abc123"}, "reason")
            update_pending_status(task_id, "approved")
            tasks = get_pending_tasks()  # only returns 'pending'
        self.assertEqual(len(tasks), 0)  # approved task no longer in pending list


if __name__ == "__main__":
    unittest.main()
