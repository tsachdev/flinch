import re
import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import base64
import email as email_lib

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
]

TOKEN_PATH = Path(__file__).parent.parent.parent / "token.json"

TOOL_REGISTRY = {}

def tool(name):
    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn
    return decorator

def _get_service():
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def _get_body(msg):
    payload = msg.get('payload', {})
    parts = payload.get('parts', [])
    body_data = ""
    if parts:
        for part in parts:
            if part.get('mimeType') == 'text/plain':
                body_data = part.get('body', {}).get('data', '')
                break
    if not body_data:
        body_data = payload.get('body', {}).get('data', '')
    if not body_data:
        return ""
    text = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = '\n'.join(line.strip() for line in text.splitlines() if line.strip())
    lines = text.splitlines()[:10]
    return '\n'.join(lines)[:300]

@tool("get_unread_emails")
def get_unread_emails() -> dict:
    service = _get_service()
    results = service.users().messages().list(
        userId='me',
        q='is:unread',
        maxResults=20
    ).execute()

    messages = results.get('messages', [])
    emails = []
    for m in messages:
        msg = service.users().messages().get(
            userId='me', id=m['id'], format='full'
        ).execute()
        headers = {h['name']: h['value'] for h in msg['payload']['headers']}
        emails.append({
            'id':      m['id'],
            'from':    headers.get('From', ''),
            'subject': headers.get('Subject', ''),
            'date':    headers.get('Date', ''),
            'preview': _get_body(msg)
        })

    print(f"  [gmail] fetched {len(emails)} unread emails")
    return {"emails": emails}

@tool("create_draft")
def create_draft(to: str, subject: str, body: str) -> dict:
    service = _get_service()
    message = email_lib.message.EmailMessage()
    message['To'] = to
    message['Subject'] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId='me',
        body={'message': {'raw': raw}}
    ).execute()
    print(f"  [gmail] draft created → {draft['id']}")
    return {"status": "drafted", "draft_id": draft['id'], "to": to, "subject": subject}

@tool("mark_read")
def mark_read(email_id: str) -> dict:
    service = _get_service()
    service.users().messages().modify(
        userId='me',
        id=email_id,
        body={'removeLabelIds': ['UNREAD']}
    ).execute()
    return {"status": "marked_read", "email_id": email_id}

@tool("delete_email")
def delete_email(email_id: str) -> dict:
    service = _get_service()
    service.users().messages().trash(
        userId='me',
        id=email_id
    ).execute()
    print(f"  [gmail] trashed → {email_id}")
    return {"status": "trashed", "email_id": email_id}

@tool("add_to_pending_queue")
def add_to_pending_queue(email_id: str, subject: str, sender: str, reason: str) -> dict:
    from eventqueue.bus import enqueue_pending
    task_id = enqueue_pending(
        task_type="delete_email",
        payload={"email_id": email_id, "subject": subject, "sender": sender},
        reason=reason
    )
    print(f"  [pending] queued deletion task → {task_id[:8]}")
    return {"status": "queued", "task_id": task_id, "email_id": email_id}

TOOLS = [
    {
        "name": "get_unread_emails",
        "description": "Fetch unread emails from Gmail inbox",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "create_draft",
        "description": "Create a Gmail draft reply",
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
        "description": "Mark an email as read",
        "input_schema": {
            "type": "object",
            "properties": {"email_id": {"type": "string"}},
            "required": ["email_id"]
        }
    },
    {
        "name": "delete_email",
        "description": "Move an email to trash",
        "input_schema": {
            "type": "object",
            "properties": {"email_id": {"type": "string"}},
            "required": ["email_id"]
        }
    },
    {
        "name": "add_to_pending_queue",
        "description": "Add an email deletion to the pending approval queue",
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
