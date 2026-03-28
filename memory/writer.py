import json
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).parent

def write_session(result: dict) -> Path:
    role       = result.get("role", "unknown")
    session_id = result["session_id"]
    event_type = result["event_type"]
    payload    = result["payload"]
    response   = result["response"]
    tool_calls = result.get("tool_calls", [])
    tokens     = result.get("tokens", 0)
    timestamp  = datetime.utcnow().isoformat()

    sessions_dir = MEMORY_DIR / "roles" / role / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Session — {timestamp}",
        f"",
        f"## Trigger",
        f"type: {event_type}",
        f"session_id: {session_id}",
    ]
    for k, v in payload.items():
        lines.append(f"payload.{k}: {v}")

    lines += ["", "## Actions taken"]
    for i, call in enumerate(tool_calls, 1):
        lines.append(
            f"{i}. `{call['tool']}({json.dumps(call['input'])})` "
            f"→ {json.dumps(call['result'])}"
        )

    lines += [
        "", "## Agent summary",
        response.strip(),
        "", "## Metadata",
        f"tokens: {tokens}",
        f"timestamp: {timestamp}",
    ]

    observations = _extract_observations(tool_calls, payload, role)
    if observations:
        lines += ["", "## Observations"]
        for obs in observations:
            lines.append(f"- {obs}")

    content  = "\n".join(lines)
    filename = timestamp.replace(":", "-").replace(".", "-")[:19] + ".md"
    filepath = sessions_dir / filename
    filepath.write_text(content)
    print(f"[memory] session note → memory/roles/{role}/sessions/{filename}")

    _upsert_entities(tool_calls, payload, role, timestamp)

    return filepath

def _upsert_entities(tool_calls: list, payload: dict, role: str, timestamp: str):
    entities_dir = MEMORY_DIR / "shared" / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)

    for call in tool_calls:
        # customer entity
        if call["tool"] == "get_customer" and call["result"].get("customer_id"):
            r   = call["result"]
            cid = r["customer_id"]
            _upsert_customer(entities_dir, cid, r, role, timestamp)

        # known issue — loyalty points failure
        if call["tool"] == "apply_loyalty_points" and call["result"].get("status") == "success":
            _upsert_known_issue(
                entities_dir,
                issue_key="loyalty_points_accrual_failure",
                ticket_id=payload.get("ticket_id", "unknown"),
                order_id=payload.get("order_id", "unknown"),
                timestamp=timestamp
            )

def _upsert_customer(entities_dir: Path, cid: str, data: dict, role: str, timestamp: str):
    filepath = entities_dir / "customers.md"
    existing = filepath.read_text() if filepath.exists() else ""

    marker = f"customer_id: {cid}"
    entry = (
        f"\n## {data.get('name', 'Unknown')} — customer_id: {cid}\n"
        f"- email: {data.get('email', 'unknown')}\n"
        f"- loyalty_tier: {data.get('loyalty_tier', 'unknown')}\n"
        f"- account_status: {data.get('account_status', 'unknown')}\n"
        f"- last_seen_by: {role} on {timestamp[:10]}\n"
    )

    if marker in existing:
        return  # already exists — don't overwrite, preserve manual edits

    if not existing:
        filepath.write_text("# Known customers\n" + entry)
    else:
        filepath.write_text(existing.rstrip() + "\n" + entry)

    print(f"[memory] entity upserted → customers.md (id: {cid})")

def _upsert_known_issue(entities_dir: Path, issue_key: str,
                         ticket_id: str, order_id: str, timestamp: str):
    filepath = entities_dir / "known_issues.md"
    existing = filepath.read_text() if filepath.exists() else ""

    ticket_ref = f"ticket #{ticket_id}"
    if ticket_ref in existing:
        return  # already recorded

    if issue_key in existing:
        # issue exists — append the new ticket reference
        updated = existing.replace(
            "tickets_seen:",
            f"tickets_seen: {ticket_ref} ({timestamp[:10]}),"
        )
        filepath.write_text(updated)
    else:
        entry = (
            f"\n## {issue_key.replace('_', ' ').title()} — {timestamp[:10]}\n"
            f"- symptom: points_applied = false on eligible orders\n"
            f"- status: open\n"
            f"- tickets_seen: {ticket_ref} ({timestamp[:10]})\n"
            f"- affected_order: {order_id}\n"
            f"- recommendation: escalate to engineering if pattern repeats\n"
        )
        if not existing:
            filepath.write_text("# Known systemic issues\n" + entry)
        else:
            filepath.write_text(existing.rstrip() + "\n" + entry)

    print(f"[memory] entity upserted → known_issues.md (ticket: {ticket_id})")

def _extract_observations(tool_calls: list, payload: dict, role: str) -> list:
    observations = []
    for call in tool_calls:
        if call["tool"] == "apply_loyalty_points":
            observations.append(
                f"Loyalty points manually applied for order "
                f"{payload.get('order_id', 'unknown')} — possible systemic issue"
            )
        if call["tool"] == "update_ticket":
            observations.append(
                f"Ticket {payload.get('ticket_id', 'unknown')} "
                f"closed with status: {call['result'].get('new_status')}"
            )
    return observations