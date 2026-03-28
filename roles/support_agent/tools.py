TOOL_REGISTRY = {}

def tool(name):
    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn
    return decorator

@tool("get_customer")
def get_customer(customer_id: str) -> dict:
    return {"customer_id": customer_id, "name": "Sarah Mitchell",
            "email": "sarah.mitchell@example.com", "loyalty_tier": "gold",
            "points_balance": 0, "account_status": "active"}

@tool("get_order")
def get_order(order_id: str) -> dict:
    return {"order_id": order_id, "customer_id": "1204", "total": 124.99,
            "date": "2026-03-10", "payment_method": "credit_card",
            "points_applied": False, "discount_code": None}

@tool("get_loyalty_transactions")
def get_loyalty_transactions(customer_id: str) -> dict:
    return {"customer_id": customer_id, "transactions": [],
            "note": "No transactions found"}

@tool("apply_loyalty_points")
def apply_loyalty_points(customer_id: str, order_id: str, reason: str) -> dict:
    return {"status": "success", "customer_id": customer_id,
            "order_id": order_id, "points_applied": 124, "new_balance": 124}

@tool("send_notification")
def send_notification(customer_id: str, ticket_id: str, message: str) -> dict:
    return {"status": "sent", "customer_id": customer_id,
            "ticket_id": ticket_id, "channel": "email"}

@tool("update_ticket")
def update_ticket(ticket_id: str, status: str, resolution_notes: str) -> dict:
    return {"status": "updated", "ticket_id": ticket_id, "new_status": status}

TOOLS = [
    {"name": "get_customer", "description": "Fetch customer profile",
     "input_schema": {"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]}},
    {"name": "get_order", "description": "Fetch order details",
     "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}},
    {"name": "get_loyalty_transactions", "description": "Fetch loyalty transaction history",
     "input_schema": {"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]}},
    {"name": "apply_loyalty_points", "description": "Manually apply loyalty points",
     "input_schema": {"type": "object", "properties": {
         "customer_id": {"type": "string"}, "order_id": {"type": "string"}, "reason": {"type": "string"}},
         "required": ["customer_id", "order_id", "reason"]}},
    {"name": "send_notification", "description": "Send notification to customer",
     "input_schema": {"type": "object", "properties": {
         "customer_id": {"type": "string"}, "ticket_id": {"type": "string"}, "message": {"type": "string"}},
         "required": ["customer_id", "ticket_id", "message"]}},
    {"name": "update_ticket", "description": "Update ticket status",
     "input_schema": {"type": "object", "properties": {
         "ticket_id": {"type": "string"}, "status": {"type": "string"}, "resolution_notes": {"type": "string"}},
         "required": ["ticket_id", "status", "resolution_notes"]}},
]