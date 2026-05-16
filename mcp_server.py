"""Flinch MCP Server — exposes agent data to Claude Desktop."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP
import httpx

try:
    from config import CONSOLE_URL
except ImportError:
    CONSOLE_URL = "http://localhost:5001"

mcp = FastMCP("flinch", dependencies=["httpx"])


@mcp.tool()
async def get_email_summary() -> str:
    """Get the latest email review summary and recent session activity."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CONSOLE_URL}/api/email-summary")
        data = r.json()
    if data.get("summary"):
        return f"Summary ({data['summary_date']}):\n{data['summary']}"
    if data.get("recent_sessions"):
        lines = [f"- {s['timestamp']}: {s['preview']}" for s in data["recent_sessions"]]
        return "Recent sessions:\n" + "\n".join(lines)
    return "No email review data available."


@mcp.tool()
async def get_market_summary() -> str:
    """Get the latest market watcher summary and earnings information."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CONSOLE_URL}/api/market-summary")
        data = r.json()
    if data.get("summary"):
        return f"Summary ({data['summary_date']}):\n{data['summary']}"
    if data.get("recent_sessions"):
        lines = [f"- {s['timestamp']}: {s['preview']}" for s in data["recent_sessions"]]
        return "Recent sessions:\n" + "\n".join(lines)
    return "No market data available."


@mcp.tool()
async def get_pending_approvals() -> str:
    """Get pending email deletion approvals that need review."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CONSOLE_URL}/api/pending")
        data = r.json()
    if not data["pending"]:
        return "No pending approvals."
    lines = []
    for item in data["pending"]:
        lines.append(f"[{item['id'][:8]}] {item['sender']} — {item['subject']} ({item['source']}) — {item['reason']}")
    return f"{data['count']} pending approvals:\n" + "\n".join(lines)


@mcp.tool()
async def get_watchlist() -> str:
    """Get current stock watchlist with prices and daily changes."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CONSOLE_URL}/api/watchlist")
        data = r.json()
    if not data["stocks"]:
        return "No watchlist data."
    lines = []
    for s in data["stocks"]:
        try:
            chg = float(s["change"])
            arrow = "▲" if chg >= 0 else "▼"
            lines.append(f"{s['symbol']}: ${s['price']} {arrow}{abs(chg):.2f}")
        except (ValueError, TypeError):
            lines.append(f"{s['symbol']}: ${s['price']}")
    return f"{len(data['stocks'])} stocks:\n" + "\n".join(lines)


@mcp.tool()
async def approve_email(task_id: str) -> str:
    """Approve a pending email deletion. Use the task ID from get_pending_approvals."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CONSOLE_URL}/approve/{task_id}", follow_redirects=True)
    return f"Approved: {task_id}"


@mcp.tool()
async def reject_email(task_id: str) -> str:
    """Reject a pending email deletion (keep the email). Use the task ID from get_pending_approvals."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CONSOLE_URL}/reject/{task_id}", follow_redirects=True)
    return f"Rejected: {task_id}"


@mcp.tool()
async def update_skill(role: str, feedback: str) -> str:
    """Update an agent's skill/behaviour. Role is 'email_reviewer' or 'market_watcher'. Feedback is natural language describing the change."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{CONSOLE_URL}/update-skill/{role}",
            json={"feedback": feedback},
        )
        data = r.json()
    if data.get("status") == "ok":
        return f"Skill updated for {role}."
    return f"Error: {data.get('error', 'unknown')}"


if __name__ == "__main__":
    mcp.run()
