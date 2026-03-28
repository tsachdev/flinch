TOOL_REGISTRY = {}

def tool(name):
    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn
    return decorator

@tool("get_contact")
def get_contact(contact_id: str) -> dict:
    return {"contact_id": contact_id, "name": "Rahul Mehta",
            "relationship": "friend", "last_contact": "2026-02-28"}

@tool("flag_urgent")
def flag_urgent(contact_id: str, reason: str) -> dict:
    return {"status": "flagged", "contact_id": contact_id, "reason": reason}

@tool("draft_response")
def draft_response(contact_id: str, message: str, tone: str) -> dict:
    return {"status": "drafted", "contact_id": contact_id,
            "tone": tone, "draft": message}

TOOLS = [
    {"name": "get_contact", "description": "Look up contact relationship and history",
     "input_schema": {"type": "object", "properties": {"contact_id": {"type": "string"}}, "required": ["contact_id"]}},
    {"name": "flag_urgent", "description": "Flag a message as urgent for immediate attention",
     "input_schema": {"type": "object", "properties": {
         "contact_id": {"type": "string"}, "reason": {"type": "string"}},
         "required": ["contact_id", "reason"]}},
    {"name": "draft_response", "description": "Draft a response to a message",
     "input_schema": {"type": "object", "properties": {
         "contact_id": {"type": "string"}, "message": {"type": "string"}, "tone": {"type": "string"}},
         "required": ["contact_id", "message", "tone"]}},
]