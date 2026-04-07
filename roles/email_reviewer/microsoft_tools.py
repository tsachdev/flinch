import re
import json
import base64
import email as email_lib
from pathlib import Path
from datetime import datetime, timezone

import msal
import requests

TOKEN_PATH = Path(__file__).parent.parent.parent / "microsoft_token.json"
GRAPH_BASE  = "https://graph.microsoft.com/v1.0"

SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
]

TOOL_REGISTRY = {}

def tool(name):
    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn
    return decorator

# ── Auth ──────────────────────────────────────────────────────────────

def _get_token() -> str:
    """Load token from file, refresh if expired."""
    from config import MICROSOFT_CLIENT_ID, MICROSOFT_TENANT_ID

    token_data = json.loads(TOKEN_PATH.read_text())

    app = msal.PublicClientApplication(
        MICROSOFT_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}",
    )

    # Try silent refresh first
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            TOKEN_PATH.write_text(json.dumps(result, indent=2))
            return result["access_token"]

    # Fall back to refresh token in file
    if "refresh_token" in token_data:
        result = app.acquire_token_by_refresh_token(
            token_data["refresh_token"], scopes=SCOPES
        )
        if result and "access_token" in result:
            TOKEN_PATH.write_text(json.dumps(result, indent=2))
            return result["access_token"]

    raise RuntimeError(
        "[microsoft] Token expired and could not be refreshed. "
        "Run microsoft_auth.py to re-authenticate."
    )

def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}

# ── Body extraction ───────────────────────────────────────────────────

def _get_body(message: dict) -> str:
    """Extract plain text preview from a Graph API message object."""
    body = message.get("body", {})
    content = body.get("content", "")
    content_type = body.get("contentType", "text")

    if content_type == "html":
        # Strip style blocks before removing tags
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
        content = re.sub(r'<[^>]+>', ' ', content)

    content = re.sub(r'https?://\S+', '', content)
    content = re.sub(r'[ \t]+', ' ', content)
    content = '\n'.join(line.strip() for line in content.splitlines() if line.strip())
    lines = content.splitlines()[:10]
    return '\n'.join(lines)[:300]

# ── Tools ─────────────────────────────────────────────────────────────

@tool("get_unread_emails")
def get_unread_emails() -> dict:
    """Fetch unread emails from Microsoft inbox via Graph API."""
    url = (
        f"{GRAPH_BASE}/me/mailFolders/inbox/messages"
        "?$filter=isRead eq false"
        "&$select=id,from,subject,receivedDateTime,bodyPreview,body"
        "&$top=20"
        "&$orderby=receivedDateTime desc"
    )
    resp = requests.get(url, headers=_headers())
    resp.raise_for_status()
    messages = resp.json().get("value", [])

    emails = []
    for m in messages:
        emails.append({
            "id":      m["id"],
            "from":    m.get("from", {}).get("emailAddress", {}).get("address", ""),
            "subject": m.get("subject", ""),
            "date":    m.get("receivedDateTime", ""),
            "preview": _get_body(m),
        })

    print(f"  [microsoft] fetched {len(emails)} unread emails")
    return {"emails": emails}

@tool("create_draft")
def create_draft(to: str, subject: str, body: str) -> dict:
    """Create a draft reply in Microsoft Outlook via Graph API."""
    url = f"{GRAPH_BASE}/me/messages"
    payload = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": to}}],
        "isDraft": True,
    }
    resp = requests.post(url, headers=_headers(), json=payload)
    resp.raise_for_status()
    draft = resp.json()
    print(f"  [microsoft] draft created → {draft['id'][:16]}...")
    return {"status": "drafted", "draft_id": draft["id"], "to": to, "subject": subject}

@tool("mark_read")
def mark_read(email_id: str) -> dict:
    """Mark a Microsoft email as read via Graph API."""
    url = f"{GRAPH_BASE}/me/messages/{email_id}"
    resp = requests.patch(url, headers=_headers(), json={"isRead": True})
    resp.raise_for_status()
    return {"status": "marked_read", "email_id": email_id}

@tool("delete_email")
def delete_email(email_id: str) -> dict:
    """Move a Microsoft email to the Deleted Items folder via Graph API."""
    url = f"{GRAPH_BASE}/me/messages/{email_id}/move"
    resp = requests.post(url, headers=_headers(), json={"destinationId": "deleteditems"})
    resp.raise_for_status()
    print(f"  [microsoft] moved to deleted items → {email_id[:16]}...")
    return {"status": "trashed", "email_id": email_id}

@tool("add_to_pending_queue")
def add_to_pending_queue(email_id: str, subject: str, sender: str, reason: str) -> dict:
    """Add a Microsoft email deletion to the pending approval queue."""
    from eventqueue.bus import enqueue_pending
    task_id = enqueue_pending(
        task_type="delete_email_microsoft",
        payload={"email_id": email_id, "subject": subject, "sender": sender},
        reason=reason,
    )
    print(f"  [pending] queued microsoft deletion → {task_id[:8]}")
    return {"status": "queued", "task_id": task_id, "email_id": email_id}

# ── Tool schemas (identical interface to Gmail tools) ─────────────────

TOOLS = [
    {
        "name": "get_unread_emails",
        "description": "Fetch unread emails from Microsoft Outlook inbox",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "create_draft",
        "description": "Create a draft reply in Microsoft Outlook",
        "input_schema": {
            "type": "object",
            "properties": {
                "to":      {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body":    {"type": "string", "description": "Email body text"}
            },
            "required": ["to", "subject", "body"]
        }
    },
    {
        "name": "mark_read",
        "description": "Mark a Microsoft email as read",
        "input_schema": {
            "type": "object",
            "properties": {"email_id": {"type": "string"}},
            "required": ["email_id"]
        }
    },
    {
        "name": "delete_email",
        "description": "Move a Microsoft email to Deleted Items",
        "input_schema": {
            "type": "object",
            "properties": {"email_id": {"type": "string"}},
            "required": ["email_id"]
        }
    },
    {
        "name": "add_to_pending_queue",
        "description": "Add a Microsoft email deletion to the pending approval queue",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string"},
                "subject":  {"type": "string"},
                "sender":   {"type": "string"},
                "reason":   {"type": "string", "description": "Why this email should be deleted"}
            },
            "required": ["email_id", "subject", "sender", "reason"]
        }
    }
]
