from agent.registry import get_role
from agent.context import build_context

event = {
    "id":      "test-context-001",
    "type":    "support_ticket",
    "source":  "zendesk",
    "payload": {
        "ticket_id":   "5002",
        "subject":     "Loyalty points still missing",
        "customer_id": "1204",
        "order_id":    "9903"
    }
}

role = get_role("support_ticket")
context = build_context(role, event)

print("=== ASSEMBLED CONTEXT ===\n")
print(context)
print(f"\n=== TOTAL LENGTH: {len(context)} chars ===")
