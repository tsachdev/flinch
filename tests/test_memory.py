"""
Tests for memory/writer.py
Uses a temporary directory — never touches real memory files
"""
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile
import shutil


class TestMemoryWriter(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_result(self, role="support_agent", tool_calls=None):
        return {
            "role": role,
            "session_id": "test-session-001",
            "event_type": "support_ticket",
            "payload": {"ticket_id": "T001", "customer_id": "C001"},
            "response": "Ticket resolved successfully.",
            "tool_calls": tool_calls or [],
            "tokens": 512,
        }

    def test_write_session_creates_file(self):
        with patch("memory.writer.MEMORY_DIR", self.tmpdir):
            from memory.writer import write_session
            filepath = write_session(self._make_result())
        self.assertTrue(filepath.exists())

    def test_write_session_correct_directory(self):
        with patch("memory.writer.MEMORY_DIR", self.tmpdir):
            from memory.writer import write_session
            filepath = write_session(self._make_result(role="support_agent"))
        expected_dir = self.tmpdir / "roles" / "support_agent" / "sessions"
        self.assertEqual(filepath.parent, expected_dir)

    def test_write_session_file_contains_role(self):
        with patch("memory.writer.MEMORY_DIR", self.tmpdir):
            from memory.writer import write_session
            filepath = write_session(self._make_result())
        content = filepath.read_text()
        self.assertIn("support_ticket", content)

    def test_write_session_file_contains_response(self):
        with patch("memory.writer.MEMORY_DIR", self.tmpdir):
            from memory.writer import write_session
            filepath = write_session(self._make_result())
        content = filepath.read_text()
        self.assertIn("Ticket resolved successfully.", content)

    def test_write_session_file_contains_tool_calls(self):
        tool_calls = [
            {"tool": "get_customer", "input": {"customer_id": "C001"},
             "result": {"customer_id": "C001", "name": "Sarah Mitchell"}}
        ]
        with patch("memory.writer.MEMORY_DIR", self.tmpdir):
            from memory.writer import write_session
            filepath = write_session(self._make_result(tool_calls=tool_calls))
        content = filepath.read_text()
        self.assertIn("get_customer", content)

    def test_write_session_creates_parent_dirs(self):
        with patch("memory.writer.MEMORY_DIR", self.tmpdir):
            from memory.writer import write_session
            write_session(self._make_result(role="new_role"))
        expected_dir = self.tmpdir / "roles" / "new_role" / "sessions"
        self.assertTrue(expected_dir.exists())

    def test_write_session_filename_is_timestamp(self):
        with patch("memory.writer.MEMORY_DIR", self.tmpdir):
            from memory.writer import write_session
            filepath = write_session(self._make_result())
        # Filename should be a timestamp-based .md file
        self.assertTrue(filepath.name.endswith(".md"))
        # Should start with a year
        self.assertTrue(filepath.name.startswith("202"))

    def test_upsert_customer_creates_entity(self):
        tool_calls = [
            {"tool": "get_customer",
             "input": {"customer_id": "C001"},
             "result": {"customer_id": "C001", "name": "Sarah Mitchell",
                        "email": "sarah@example.com", "loyalty_tier": "gold",
                        "account_status": "active"}}
        ]
        with patch("memory.writer.MEMORY_DIR", self.tmpdir):
            from memory.writer import write_session
            write_session(self._make_result(tool_calls=tool_calls))

        customers_file = self.tmpdir / "shared" / "entities" / "customers.md"
        self.assertTrue(customers_file.exists())
        content = customers_file.read_text()
        self.assertIn("C001", content)
        self.assertIn("Sarah Mitchell", content)

    def test_upsert_customer_not_duplicated(self):
        tool_calls = [
            {"tool": "get_customer",
             "input": {"customer_id": "C001"},
             "result": {"customer_id": "C001", "name": "Sarah Mitchell",
                        "email": "sarah@example.com", "loyalty_tier": "gold",
                        "account_status": "active"}}
        ]
        with patch("memory.writer.MEMORY_DIR", self.tmpdir):
            from memory.writer import write_session
            write_session(self._make_result(tool_calls=tool_calls))
            write_session(self._make_result(tool_calls=tool_calls))

        customers_file = self.tmpdir / "shared" / "entities" / "customers.md"
        content = customers_file.read_text()
        # customer_id should appear only once
        self.assertEqual(content.count("customer_id: C001"), 1)


if __name__ == "__main__":
    unittest.main()
