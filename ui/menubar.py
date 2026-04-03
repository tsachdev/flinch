import json
import sys
import urllib.request
import rumps
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SERVER_HOST

CONSOLE_URL  = "http://localhost:5001"
STATUS_URL   = "http://localhost:5001/api/status"

class GenClawApp(rumps.App):
    def __init__(self):
        super().__init__("🦞", quit_button=None)
        self._tunnel_proc = None

        self.pending_item   = rumps.MenuItem("No pending approvals")
        self.console_item   = rumps.MenuItem("Open Console", callback=self.open_console)
        self.last_run_item  = rumps.MenuItem("Last run: —")
        self.next_run_item  = rumps.MenuItem("Next run: —")
        self.refresh_item   = rumps.MenuItem("Refresh", callback=self.refresh)
        self.quit_item      = rumps.MenuItem("Quit", callback=self.quit_app)

        self.pending_item.set_callback(self.open_console)

        self.menu = [
            self.pending_item,
            rumps.separator,
            self.console_item,
            rumps.separator,
            self.last_run_item,
            self.next_run_item,
            rumps.separator,
            self.refresh_item,
            self.quit_item,
        ]

        self._start_tunnel()
        self.refresh(None)

    # -----------------------------------------------------------------------
    # Timer
    # -----------------------------------------------------------------------

    @rumps.timer(60)
    def tick(self, _):
        self._ensure_tunnel()
        self.refresh(None)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def open_console(self, _):
        webbrowser.open(CONSOLE_URL)

    def refresh(self, _):
        status  = self._fetch_status()
        pending = status["pending_count"]
        self.title = f"🦞 {pending}" if pending > 0 else "🦞"

        if pending == 0:
            self.pending_item.title = "No pending approvals"
        elif pending == 1:
            self.pending_item.title = "1 email pending approval"
        else:
            self.pending_item.title = f"{pending} emails pending approval"

        self.last_run_item.title = f"Last run: {_format_ts(status['last_run'])}"
        self.next_run_item.title = f"Next run: {_format_ts(status['next_run'])}"

    def quit_app(self, _):
        self._kill_tunnel()
        rumps.quit_application()

    # -----------------------------------------------------------------------
    # Status API
    # -----------------------------------------------------------------------

    def _fetch_status(self) -> dict:
        try:
            with urllib.request.urlopen(STATUS_URL, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            return data
        except Exception as e:
            print(f"[menubar] status fetch error: {e}")
            return {"pending_count": 0, "last_run": "unavailable", "next_run": "unavailable"}

    # -----------------------------------------------------------------------
    # SSH tunnel
    # -----------------------------------------------------------------------

    def _start_tunnel(self):
        try:
            self._tunnel_proc = subprocess.Popen(
                ["ssh", "-N", "-L", "5001:localhost:5001", SERVER_HOST],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[menubar] tunnel started (pid {self._tunnel_proc.pid})")
        except Exception as e:
            print(f"[menubar] tunnel start failed: {e}")

    def _ensure_tunnel(self):
        if self._tunnel_proc and self._tunnel_proc.poll() is not None:
            print("[menubar] tunnel died — restarting")
            self._start_tunnel()

    def _kill_tunnel(self):
        if self._tunnel_proc:
            try:
                self._tunnel_proc.terminate()
                self._tunnel_proc.wait(timeout=3)
                print("[menubar] tunnel stopped")
            except Exception as e:
                print(f"[menubar] tunnel stop error: {e}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_ts(ts) -> str:
    """Format an ISO timestamp string from the API for display, or pass through fallback strings."""
    if not ts or ts == "unavailable":
        return ts or "unavailable"
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return _friendly_time(dt)
    except Exception:
        return ts


def _friendly_time(dt: datetime) -> str:
    now   = datetime.now(timezone.utc)
    delta = dt - now
    secs  = int(delta.total_seconds())

    if secs < -86400:
        return dt.strftime("%b %d %H:%M")
    if secs < -3600:
        return f"{abs(secs) // 3600}h ago"
    if secs < -60:
        return f"{abs(secs) // 60}m ago"
    if secs < 0:
        return "just now"
    if secs < 60:
        return "in <1m"
    if secs < 3600:
        return f"in {secs // 60}m"
    return f"in {secs // 3600}h"


if __name__ == "__main__":
    GenClawApp().run()
