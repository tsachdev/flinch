TOOL_REGISTRY = {}

def tool(name):
    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn
    return decorator

@tool("get_unread_emails")
def get_unread_emails() -> dict:
    return {"emails": [
        {"id": "e001", "from": "arvind@aptos.com",   "subject": "Bangalore hire update",    "preview": "3 candidates shortlisted..."},
        {"id": "e002", "from": "newsletter@medium.com", "subject": "Top AI stories this week", "preview": "This week in AI..."},
        {"id": "e003", "from": "pete@aptos.com",     "subject": "CAB deck review needed",   "preview": "Tushar, can you review..."},
    ]}

@tool("draft_reply")
def draft_reply(email_id: str, draft: str) -> dict:
    return {"status": "drafted", "email_id": email_id, "draft": draft}

@tool("mark_read")
def mark_read(email_id: str) -> dict:
    return {"status": "marked_read", "email_id": email_id}

TOOLS = [
    {"name": "get_unread_emails", "description": "Fetch unread emails from inbox",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "draft_reply", "description": "Draft a reply to an email",
     "input_schema": {"type": "object", "properties": {
         "email_id": {"type": "string"}, "draft": {"type": "string"}},
         "required": ["email_id", "draft"]}},
    {"name": "mark_read", "description": "Mark an email as read",
     "input_schema": {"type": "object", "properties": {"email_id": {"type": "string"}}, "required": ["email_id"]}},
]