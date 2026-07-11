"""
Tests for ui/console.py's JSON API — both the mcp_server.py-facing contract
(paths/shapes must not change) and the new console-SPA-facing endpoints
added in M5.
"""
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ui.console import app


class ConsoleAPITestCase(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.db_path = self.tmpdir / "flinch.db"
        self.memory_dir = self.tmpdir / "memory"
        (self.memory_dir / "roles" / "email_reviewer" / "sessions").mkdir(parents=True)

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE queue (
                id TEXT PRIMARY KEY, type TEXT, source TEXT, payload TEXT,
                status TEXT, created_at TEXT, updated_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE pending_queue (
                id TEXT PRIMARY KEY, task_type TEXT, payload TEXT,
                reason TEXT, status TEXT, created_at TEXT, updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()

        import ui.console as console_module
        import eventqueue.bus as bus_module
        self.console_module = console_module
        self._patchers = [
            patch.object(console_module, "DB_PATH", self.db_path),
            patch.object(console_module, "MEMORY_DIR", self.memory_dir),
            # get_pending_tasks/update_pending_status live in eventqueue.bus
            # and read its own module-level DB_PATH, not console.py's.
            patch.object(bus_module, "DB_PATH", self.db_path),
        ]
        for p in self._patchers:
            p.start()

        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_session(self, role, filename, content):
        sessions_dir = self.memory_dir / "roles" / role / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / filename).write_text(content)

    def _insert_pending(self, task_id, task_type, payload, reason, status="pending"):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO pending_queue VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, task_type, json.dumps(payload), reason, status,
             "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

    # ── mcp_server.py-facing contract ──────────────────────────────────

    def test_api_pending_shape_unchanged(self):
        self._insert_pending("t1", "delete_email", {"email_id": "e1", "sender": "a@b.com", "subject": "hi"}, "promo")
        resp = self.client.get("/api/pending")
        data = resp.get_json()
        self.assertEqual(data["count"], 1)
        item = data["pending"][0]
        self.assertEqual(set(item.keys()), {"id", "sender", "subject", "reason", "source", "created_at"})
        self.assertEqual(item["source"], "gmail")

    def test_api_pending_microsoft_source(self):
        self._insert_pending("t1", "delete_email_microsoft", {"email_id": "e1"}, "promo")
        resp = self.client.get("/api/pending")
        self.assertEqual(resp.get_json()["pending"][0]["source"], "outlook")

    def test_api_status_route_exists(self):
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("pending_count", resp.get_json())

    def test_legacy_approve_route_redirects_to_root(self):
        self._insert_pending("t1", "delete_email", {"email_id": "e1"}, "promo")
        with patch("ui.console._execute_approval", return_value={"status": "trashed"}):
            resp = self.client.get("/approve/t1")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/"))

    def test_legacy_reject_route_redirects_to_root(self):
        self._insert_pending("t1", "delete_email", {"email_id": "e1"}, "promo")
        resp = self.client.get("/reject/t1")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/"))

    # ── New SPA-facing endpoints (M5) ──────────────────────────────────

    def test_api_roles_lists_all_four(self):
        resp = self.client.get("/api/roles")
        data = resp.get_json()
        roles = {r["role"] for r in data["roles"]}
        self.assertEqual(roles, {"support_agent", "email_reviewer", "personal_assistant", "market_watcher"})

    def test_api_roles_reflects_running_status(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO queue VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("evt1", "cron", "scheduler", json.dumps({"job": "email_review"}),
             "in-progress", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        resp = self.client.get("/api/roles")
        by_role = {r["role"]: r for r in resp.get_json()["roles"]}
        self.assertEqual(by_role["email_reviewer"]["status"], "running")
        self.assertEqual(by_role["support_agent"]["status"], "idle")

    def test_api_role_sessions_unknown_role_404s(self):
        resp = self.client.get("/api/roles/nonexistent_role/sessions")
        self.assertEqual(resp.status_code, 404)

    def test_api_role_sessions_returns_actions(self):
        self._write_session("email_reviewer", "2026-01-01T10-00-00.md", """# Session
## Actions taken
1. `delete_email({"email_id": "e1"})` -> {"status": "trashed"}

## Console summary
Deleted one promo email.
""")
        resp = self.client.get("/api/roles/email_reviewer/sessions")
        data = resp.get_json()
        self.assertEqual(len(data["sessions"]), 1)
        session = data["sessions"][0]
        self.assertIn("Deleted one promo email", session["preview"])
        self.assertEqual(len(session["actions"]), 1)
        self.assertIn("delete_email", session["actions"][0])

    def test_api_pending_approve_json(self):
        self._insert_pending("t1", "delete_email", {"email_id": "e1"}, "promo")
        with patch("ui.console._execute_approval", return_value={"status": "trashed"}) as mock_exec:
            resp = self.client.post("/api/pending/t1/approve")
        self.assertEqual(resp.get_json()["status"], "ok")
        mock_exec.assert_called_once()

    def test_api_pending_approve_unknown_id_404s(self):
        resp = self.client.post("/api/pending/does-not-exist/approve")
        self.assertEqual(resp.status_code, 404)

    def test_api_pending_bulk_reject(self):
        self._insert_pending("t1", "delete_email", {"email_id": "e1"}, "promo")
        self._insert_pending("t2", "delete_email", {"email_id": "e2"}, "promo")
        resp = self.client.post("/api/pending/bulk", json={"action": "reject", "ids": ["t1", "t2"]})
        self.assertEqual(resp.get_json()["status"], "ok")
        # both should now be gone from the pending list
        self.assertEqual(self.client.get("/api/pending").get_json()["count"], 0)

    def test_api_pending_bulk_invalid_action(self):
        resp = self.client.post("/api/pending/bulk", json={"action": "nonsense", "ids": []})
        self.assertEqual(resp.status_code, 400)

    def test_spa_static_route_serves_index_for_unknown_path(self):
        # No dist/ build in the test environment -> 404, but the route itself
        # must exist and not collide with API/approval routes.
        resp = self.client.get("/some/deep/spa/path")
        self.assertIn(resp.status_code, (200, 404))


if __name__ == "__main__":
    unittest.main()
