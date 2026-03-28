TOOL_REGISTRY = {}

def tool(name):
    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn
    return decorator

@tool("get_inventory")
def get_inventory(product_id: str) -> dict:
    return {"product_id": product_id, "name": "Slim Fit Jeans - Indigo",
            "stock": 24, "sizes": ["28", "30", "32", "34"], "price": 89.99}

@tool("get_interested_customers")
def get_interested_customers(product_id: str) -> dict:
    return {"product_id": product_id, "customers": [
        {"id": "3001", "name": "James Park",  "size": "32", "last_purchase": "2026-01-15"},
        {"id": "3002", "name": "Maria Lopez", "size": "30", "last_purchase": "2026-02-20"},
    ]}

@tool("send_product_alert")
def send_product_alert(customer_id: str, product_id: str, message: str) -> dict:
    return {"status": "sent", "customer_id": customer_id,
            "product_id": product_id, "channel": "sms"}

TOOLS = [
    {"name": "get_inventory", "description": "Check inventory levels for a product",
     "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}},
    {"name": "get_interested_customers", "description": "Get customers who may want this product",
     "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}},
    {"name": "send_product_alert", "description": "Send product arrival alert to customer",
     "input_schema": {"type": "object", "properties": {
         "customer_id": {"type": "string"}, "product_id": {"type": "string"}, "message": {"type": "string"}},
         "required": ["customer_id", "product_id", "message"]}},
]