TOOL_REGISTRY = {}

def tool(name: str):
    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn
    return decorator

def run_tool(name: str, **kwargs) -> dict:
    if name not in TOOL_REGISTRY:
        return {"error": f"unknown tool: {name}"}
    print(f"  [tool] {name}({', '.join(f'{k}={v}' for k,v in kwargs.items())})")
    try:
        result = TOOL_REGISTRY[name](**kwargs)
        print(f"  [tool] → {result}")
        return result
    except Exception as e:
        print(f"  [tool] error: {e}")
        return {"error": str(e)}

@tool("get_customer")
def get_customer(customer_id: str) -> dict:
    return {
        "customer_id": customer_id,
        "name": "Sarah Mitchell",
        "email": "sarah.mitchell@example.com",
        "loyalty_tier": "gold",
        "points_balance": 0,
        "account_status": "active"
    }

@tool("get_order")
def get_order(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "customer_id": "1204",
        "total": 124.99,
        "date": "2026-03-10",
        "payment_method": "credit_card",
        "points_applied": False,
        "discount_code": None
    }

@tool("get_loyalty_transactions")
def get_loyalty_transactions(customer_id: str) -> dict:
    return {
        "customer_id": customer_id,
        "transactions": [],
        "note": "No transactions found for order 9902"
    }

@tool("apply_loyalty_points")
def apply_loyalty_points(customer_id: str, order_id: str, reason: str) -> dict:
    points = 124
    return {
        "status": "success",
        "customer_id": customer_id,
        "order_id": order_id,
        "points_applied": points,
        "new_balance": points,
        "reason": reason
    }

@tool("send_notification")
def send_notification(customer_id: str, ticket_id: str, message: str) -> dict:
    return {
        "status": "sent",
        "customer_id": customer_id,
        "ticket_id": ticket_id,
        "channel": "email"
    }

@tool("update_ticket")
def update_ticket(ticket_id: str, status: str, resolution_notes: str) -> dict:
    return {
        "status": "updated",
        "ticket_id": ticket_id,
        "new_status": status
    }