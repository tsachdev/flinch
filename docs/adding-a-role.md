# Adding a role to Flinch

This guide walks through adding a new agent role from scratch. By the end you'll have a working role that receives events, runs tools, and writes to memory.

We'll build a `billing_agent` as the worked example — an agent that handles inbound billing queries.

---

## How roles work

Each role in Flinch has four components:

- **PERSONA** — the system prompt that defines how the agent behaves
- **TOOLS** — the functions the agent can call (defined in two parts: the schema Claude sees, and the Python implementation)
- **Registry entry** — maps a trigger type to the role
- **Gateway handler** — defines what happens when that trigger fires

Skills (SKILL.md files) are optional but recommended for anything beyond basic behaviour.

---

## Step 1 — Create the role folder

```bash
mkdir -p roles/billing_agent
touch roles/billing_agent/__init__.py
touch roles/billing_agent/role.py
touch roles/billing_agent/tools.py
```

---

## Step 2 — Write the persona (`role.py`)

The persona is a plain string. It tells the agent who it is, what it does, and any rules it must follow.

```python
# roles/billing_agent/role.py

PERSONA = """You are Flinch's billing agent.
You handle inbound billing queries by looking up invoices and account status.
Always retrieve the invoice before responding to the customer.
If a charge looks incorrect, escalate rather than issuing a refund directly.
Always notify the customer once the query is resolved."""
```

Keep it focused. One role, one job. Constraints ("always", "never", "escalate if") belong here.

---

## Step 3 — Write the tools (`tools.py`)

Tools have two parts that must stay in sync: the **Python implementation** registered in `TOOL_REGISTRY`, and the **schema** in `TOOLS` that Claude uses to decide when and how to call them.

```python
# roles/billing_agent/tools.py

TOOL_REGISTRY = {}

def tool(name):
    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn
    return decorator

# ── Implementations ───────────────────────────

@tool("get_invoice")
def get_invoice(invoice_id: str) -> dict:
    # Replace with your real data source
    return {
        "invoice_id": invoice_id,
        "customer_id": "4001",
        "amount": 149.99,
        "status": "unpaid",
        "due_date": "2026-04-15",
    }

@tool("get_account_status")
def get_account_status(customer_id: str) -> dict:
    return {
        "customer_id": customer_id,
        "name": "Alex Johnson",
        "email": "alex.johnson@example.com",
        "account_status": "active",
        "outstanding_balance": 149.99,
    }

@tool("send_notification")
def send_notification(customer_id: str, ticket_id: str, message: str) -> dict:
    return {"status": "sent", "customer_id": customer_id,
            "ticket_id": ticket_id, "channel": "email"}

# ── Schemas (what Claude sees) ────────────────

TOOLS = [
    {
        "name": "get_invoice",
        "description": "Fetch invoice details by invoice ID",
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"}
            },
            "required": ["invoice_id"]
        }
    },
    {
        "name": "get_account_status",
        "description": "Fetch customer account status and outstanding balance",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"}
            },
            "required": ["customer_id"]
        }
    },
    {
        "name": "send_notification",
        "description": "Send a notification to the customer",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "ticket_id":   {"type": "string"},
                "message":     {"type": "string"}
            },
            "required": ["customer_id", "ticket_id", "message"]
        }
    },
]
```

**Important:** every tool in `TOOLS` must have a matching entry in `TOOL_REGISTRY` with the same name. If they're out of sync, Claude will try to call a tool and get a silent failure.

---

## Step 4 — Register the role (`agent/registry.py`)

Open `agent/registry.py` and add your trigger type and role name to `TRIGGER_TO_ROLE`:

```python
TRIGGER_TO_ROLE = {
    "support_ticket": "support_agent",
    "cron":           "email_reviewer",
    "message":        "personal_assistant",
    "billing_query":  "billing_agent",   # ← add this
}
```

If your role needs more than the default 1024 token budget, add it to `ROLE_MAX_TOKENS`:

```python
ROLE_MAX_TOKENS = {
    "email_reviewer": 8192,
    "billing_agent":  2048,   # ← add this if needed
}
```

---

## Step 5 — Add a gateway handler (`main.py`)

Open `main.py` and add a handler for your trigger type using the `@register` decorator. Look at how existing handlers are written and follow the same pattern:

```python
@register("billing_query")
def handle_billing_query(event: dict):
    role = get_role("billing_query")
    payload = event.get("payload", {})
    run_agent(role, f"Billing query received: {payload}")
```

The string passed to `run_agent` is the initial user message the agent sees. Include the key payload fields so the agent has context to act on immediately.

---

## Step 6 — Enqueue a test event

With the agent loop running (`python main.py`), open a second terminal and enqueue a test event directly into the queue:

```python
# test_billing.py
from eventqueue.bus import enqueue

enqueue("billing_query", {
    "invoice_id": "INV-9001",
    "customer_id": "4001",
    "query": "Customer is disputing charge on invoice INV-9001"
})
```

```bash
python test_billing.py
```

Watch the main terminal — you should see the gateway route the event and the agent loop execute.

---

## Step 7 — Add a skill (optional but recommended)

Skills are Markdown files that give the agent additional context or behaviour rules for specific situations — without changing any code.

```bash
mkdir -p skills/roles/billing_agent
touch skills/roles/billing_agent/dispute-handling.md
```

```markdown
# Dispute Handling

When a customer disputes a charge:
1. Always retrieve the invoice first with get_invoice
2. Check account status with get_account_status
3. If the charge matches the invoice, explain the charge clearly to the customer
4. If the charge does NOT match, escalate — do not issue a refund directly
5. Always close with a notification to the customer confirming next steps
```

Skills are loaded automatically at runtime — no code changes needed.

---

## Checklist

Before considering a role complete:

- [ ] `roles/billing_agent/__init__.py` exists (can be empty)
- [ ] `roles/billing_agent/role.py` has a `PERSONA` string
- [ ] `roles/billing_agent/tools.py` has matching `TOOL_REGISTRY` and `TOOLS`
- [ ] Trigger type added to `TRIGGER_TO_ROLE` in `agent/registry.py`
- [ ] Handler added in `main.py`
- [ ] Test event enqueues and routes correctly
- [ ] Session note written to `memory/roles/billing_agent/sessions/`

---

## Common mistakes

**Tool name mismatch** — the name in `TOOLS` and the key in `TOOL_REGISTRY` must be identical strings. A mismatch causes silent failures where Claude calls a tool and gets no response.

**Persona too vague** — if the agent behaves unpredictably, tighten the persona. Add explicit rules: "always X before Y", "never Z without checking W". Constraints in the persona are cheaper than debugging agent behaviour at runtime.

**Token budget too low** — if the agent is cutting off mid-task, increase `max_tokens` for the role in `ROLE_MAX_TOKENS`. The `email_reviewer` uses 8192 for this reason.
