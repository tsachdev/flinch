#!/usr/bin/env python
"""Shadow-mode comparison: runs a fixture through both the legacy and the
DeepAgents agent loop for a role, then diffs the *decisions* — which tools
got called with which key arguments — rather than the free-text LLM
summary.

Real LLM calls are made. email_reviewer's fixtures fake the Gmail tools (no
real Gmail calls) and redirect flinch.db/flinch_checkpoints.db to a temp
dir. support_agent and personal_assistant's tools are already fully mock
(no real backend) so their fixtures run unmodified. market_watcher's
fixtures fake yfinance/Gmail-send so no real network calls or emails are
sent.

Usage:
    python scripts/shadow_compare.py                        # every role, every fixture
    python scripts/shadow_compare.py email_reviewer          # one role, every fixture
    python scripts/shadow_compare.py email_reviewer 01       # one role, matching fixture(s)
"""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES_ROOT = Path(__file__).parent.parent / "tests" / "fixtures"


def _run_legacy(event):
    from agent.loop import run_agent
    start = time.time()
    result = run_agent(event)
    return result, time.time() - start


def _run_deepagents(event):
    from agent_deepagents.loop import run_agent
    start = time.time()
    result = run_agent(event)
    return result, time.time() - start


def _diff_tool_calls(legacy_calls, deepagents_calls, key_fn):
    """key_fn(call) -> a hashable summary of the decision this tool call
    represents (e.g. (tool_name, email_id)). Returns the set-symmetric-
    difference of decisions made by each backend."""
    legacy_set = {key_fn(c) for c in legacy_calls}
    deepagents_set = {key_fn(c) for c in deepagents_calls}
    return {
        "legacy_only": sorted(legacy_set - deepagents_set, key=str),
        "deepagents_only": sorted(deepagents_set - legacy_set, key=str),
    }


def _base_report(fixture_path, fixture, legacy_result, legacy_time, deepagents_result, deepagents_time, mismatches):
    return {
        "fixture": fixture_path.name,
        "flexible": fixture.get("flexible", False),
        "mismatches": mismatches,
        "legacy_tokens": legacy_result["tokens"],
        "deepagents_tokens": deepagents_result["tokens"],
        "legacy_seconds": round(legacy_time, 2),
        "deepagents_seconds": round(deepagents_time, 2),
    }


# ---------------------------------------------------------------------------
# email_reviewer
# ---------------------------------------------------------------------------

def _fake_email_tools(fixture_emails):
    def get_unread_emails():
        return {"emails": fixture_emails}

    def mark_read(email_id):
        return {"status": "marked_read", "email_id": email_id}

    def delete_email(email_id):
        return {"status": "trashed", "email_id": email_id}

    def create_draft(to, subject, body):
        return {"status": "drafted", "draft_id": "fake-draft-id", "to": to, "subject": subject}

    return {
        "get_unread_emails": get_unread_emails,
        "mark_read": mark_read,
        "delete_email": delete_email,
        "create_draft": create_draft,
    }


def _email_decisions(tool_calls):
    decisions = {}
    drafts = []
    for call in tool_calls:
        tool, args = call["tool"], call["input"]
        if tool == "delete_email":
            decisions[args["email_id"]] = "deleted"
        elif tool == "add_to_pending_queue":
            decisions[args["email_id"]] = "queued_for_approval"
        elif tool == "mark_read":
            prior = decisions.get(args["email_id"], "")
            decisions[args["email_id"]] = (prior + "+marked_read").lstrip("+")
        elif tool == "create_draft":
            drafts.append({"to": args.get("to"), "subject": args.get("subject")})
    return decisions, drafts


def compare_email_reviewer_fixture(fixture_path: Path) -> dict:
    fixture = json.loads(fixture_path.read_text())
    fixture_emails = fixture["emails"]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_flinch_db = Path(tmpdir) / "flinch.db"
        tmp_checkpoint_db = Path(tmpdir) / "flinch_checkpoints.db"

        import roles.email_reviewer.tools as gmail_tools
        import agent_deepagents.checkpointer as checkpointer
        import agent_deepagents.approval as approval

        original_registry = dict(gmail_tools.TOOL_REGISTRY)
        gmail_tools.TOOL_REGISTRY.update(_fake_email_tools(fixture_emails))

        event = {"id": f"shadow-{fixture_path.stem}", "type": "cron", "payload": {"job": "email_review"}}

        with patch.object(checkpointer, "CHECKPOINT_DB_PATH", tmp_checkpoint_db), \
             patch("eventqueue.bus.DB_PATH", tmp_flinch_db):
            checkpointer.reset()
            approval.reset()
            try:
                legacy_result, legacy_time = _run_legacy(event)
                deepagents_result, deepagents_time = _run_deepagents(event)
            finally:
                gmail_tools.TOOL_REGISTRY.clear()
                gmail_tools.TOOL_REGISTRY.update(original_registry)
                checkpointer.reset()
                approval.reset()

    legacy_decisions, legacy_drafts = _email_decisions(legacy_result["tool_calls"])
    deepagents_decisions, deepagents_drafts = _email_decisions(deepagents_result["tool_calls"])

    all_email_ids = {e["id"] for e in fixture_emails}
    mismatches = {}
    for email_id in all_email_ids:
        l = legacy_decisions.get(email_id, "no_action")
        d = deepagents_decisions.get(email_id, "no_action")
        if l != d:
            mismatches[email_id] = {"legacy": l, "deepagents": d}

    report = _base_report(fixture_path, fixture, legacy_result, legacy_time, deepagents_result, deepagents_time, mismatches)
    report["legacy_decisions"] = legacy_decisions
    report["deepagents_decisions"] = deepagents_decisions
    report["legacy_drafts"] = len(legacy_drafts)
    report["deepagents_drafts"] = len(deepagents_drafts)
    return report


# ---------------------------------------------------------------------------
# support_agent — tools are already fully mock (no real backend), so
# fixtures run through unmodified. Decisions diffed: which of
# {apply_loyalty_points, update_ticket-status, escalation-i.e.-no-credit}
# each backend reached for the same ticket.
# ---------------------------------------------------------------------------

def compare_support_agent_fixture(fixture_path: Path) -> dict:
    fixture = json.loads(fixture_path.read_text())
    event = {"id": f"shadow-{fixture_path.stem}", "type": "support_ticket", "payload": fixture["payload"]}

    legacy_result, legacy_time = _run_legacy(event)
    deepagents_result, deepagents_time = _run_deepagents(event)

    def key_fn(call):
        if call["tool"] == "apply_loyalty_points":
            return ("credited", call["input"].get("order_id"))
        if call["tool"] == "update_ticket":
            return ("ticket_status", call["input"].get("status"))
        if call["tool"] == "send_notification":
            # decision = "was the customer notified", not the wording
            return ("notified", call["input"].get("customer_id"))
        if call["tool"] == "get_loyalty_transactions":
            return ("investigated_loyalty", call["input"].get("customer_id"))
        return (call["tool"], json.dumps(call["input"], sort_keys=True))

    mismatches = _diff_tool_calls(legacy_result["tool_calls"], deepagents_result["tool_calls"], key_fn)
    report = _base_report(fixture_path, fixture, legacy_result, legacy_time, deepagents_result, deepagents_time,
                           mismatches if (mismatches["legacy_only"] or mismatches["deepagents_only"]) else {})
    report["legacy_tools_called"] = [c["tool"] for c in legacy_result["tool_calls"]]
    report["deepagents_tools_called"] = [c["tool"] for c in deepagents_result["tool_calls"]]
    return report


# ---------------------------------------------------------------------------
# personal_assistant — tools are already fully mock. Decisions diffed:
# flag_urgent vs draft_response (i.e. did it treat the message as urgent).
# ---------------------------------------------------------------------------

def compare_personal_assistant_fixture(fixture_path: Path) -> dict:
    fixture = json.loads(fixture_path.read_text())
    event = {"id": f"shadow-{fixture_path.stem}", "type": "message", "payload": fixture["payload"]}

    legacy_result, legacy_time = _run_legacy(event)
    deepagents_result, deepagents_time = _run_deepagents(event)

    def key_fn(call):
        if call["tool"] in ("flag_urgent", "draft_response"):
            return (call["tool"],)
        return (call["tool"], json.dumps(call["input"], sort_keys=True))

    mismatches = _diff_tool_calls(legacy_result["tool_calls"], deepagents_result["tool_calls"], key_fn)
    report = _base_report(fixture_path, fixture, legacy_result, legacy_time, deepagents_result, deepagents_time,
                           mismatches if (mismatches["legacy_only"] or mismatches["deepagents_only"]) else {})
    report["legacy_tools_called"] = [c["tool"] for c in legacy_result["tool_calls"]]
    report["deepagents_tools_called"] = [c["tool"] for c in deepagents_result["tool_calls"]]
    return report


# ---------------------------------------------------------------------------
# market_watcher — no approval step (confirmed in NOTES.md). Fakes
# yfinance-backed tools and the real Gmail send so fixtures are
# deterministic and side-effect-free.
# ---------------------------------------------------------------------------

def compare_market_watcher_fixture(fixture_path: Path) -> dict:
    fixture = json.loads(fixture_path.read_text())
    earnings_calendar = fixture["earnings_calendar"]
    stock_metrics = fixture["stock_metrics"]

    import roles.market_watcher.tools as mw_tools

    def get_earnings_calendar():
        return earnings_calendar

    def get_stock_metrics(ticker):
        return stock_metrics.get(ticker, {"ticker": ticker, "error": "no data in fixture"})

    def send_email_summary(subject, body):
        return {"status": "sent", "message_id": "fake-message-id", "subject": subject}

    original_registry = dict(mw_tools.TOOL_REGISTRY)
    mw_tools.TOOL_REGISTRY.update({
        "get_earnings_calendar": get_earnings_calendar,
        "get_stock_metrics": get_stock_metrics,
        "send_email_summary": send_email_summary,
    })

    event = {"id": f"shadow-{fixture_path.stem}", "type": "market_event", "payload": fixture["payload"]}
    try:
        legacy_result, legacy_time = _run_legacy(event)
        deepagents_result, deepagents_time = _run_deepagents(event)
    finally:
        mw_tools.TOOL_REGISTRY.clear()
        mw_tools.TOOL_REGISTRY.update(original_registry)

    def key_fn(call):
        if call["tool"] == "get_stock_metrics":
            return ("analyzed", call["input"].get("ticker"))
        if call["tool"] == "send_email_summary":
            return ("emailed",)
        return (call["tool"], json.dumps(call["input"], sort_keys=True))

    mismatches = _diff_tool_calls(legacy_result["tool_calls"], deepagents_result["tool_calls"], key_fn)
    report = _base_report(fixture_path, fixture, legacy_result, legacy_time, deepagents_result, deepagents_time,
                           mismatches if (mismatches["legacy_only"] or mismatches["deepagents_only"]) else {})
    report["legacy_tools_called"] = [c["tool"] for c in legacy_result["tool_calls"]]
    report["deepagents_tools_called"] = [c["tool"] for c in deepagents_result["tool_calls"]]
    return report


ROLE_COMPARATORS = {
    "email_reviewer": compare_email_reviewer_fixture,
    "support_agent": compare_support_agent_fixture,
    "personal_assistant": compare_personal_assistant_fixture,
    "market_watcher": compare_market_watcher_fixture,
}


def main():
    args = sys.argv[1:]
    role_filter = args[0] if args and args[0] in ROLE_COMPARATORS else None
    fixture_filter = args[1] if len(args) > 1 else (args[0] if args and not role_filter else None)

    roles = [role_filter] if role_filter else list(ROLE_COMPARATORS.keys())

    all_reports = []
    for role in roles:
        fixtures_dir = FIXTURES_ROOT / role
        if not fixtures_dir.exists():
            continue
        fixture_paths = sorted(fixtures_dir.glob("*.json"))
        if fixture_filter:
            fixture_paths = [p for p in fixture_paths if fixture_filter in p.stem]

        for path in fixture_paths:
            print(f"\n=== {role} / {path.name} ===")
            report = ROLE_COMPARATORS[role](path)
            all_reports.append(report)
            for key, value in report.items():
                if key in ("fixture", "flexible", "mismatches"):
                    continue
                print(f"  {key}: {value}")
            if report["mismatches"]:
                tag = "MISMATCH (flexible fixture, informational)" if report["flexible"] else "MISMATCH"
                print(f"  {tag}: {report['mismatches']}")
            else:
                print("  MATCH")

    hard_mismatches = [r for r in all_reports if r["mismatches"] and not r["flexible"]]
    print(f"\n{len(all_reports)} fixtures compared, {len(hard_mismatches)} hard mismatches.")
    if hard_mismatches:
        sys.exit(1)


if __name__ == "__main__":
    main()
