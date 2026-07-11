#!/usr/bin/env python
"""Shadow-mode comparison: runs a fixture (a batch of unread emails) through
both the legacy email_reviewer and the DeepAgents email_reviewer, then diffs
the *decisions* — which emails got deleted, queued for approval, marked
read, or drafted — rather than the free-text LLM summary.

Real LLM calls are made (Claude/Gemma, whichever config.ROLE_PROVIDERS
selects for email_reviewer) — no real Gmail/Outlook calls, and no writes to
the real flinch.db / flinch_checkpoints.db (both are redirected to a temp
directory for the duration of the comparison).

Usage:
    python scripts/shadow_compare.py                      # all fixtures
    python scripts/shadow_compare.py 01_obvious_promos     # one fixture
"""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "email_reviewer"


def _fake_tools(fixture_emails):
    actions = []

    def get_unread_emails():
        return {"emails": fixture_emails}

    def mark_read(email_id):
        actions.append(("mark_read", {"email_id": email_id}))
        return {"status": "marked_read", "email_id": email_id}

    def delete_email(email_id):
        actions.append(("delete_email", {"email_id": email_id}))
        return {"status": "trashed", "email_id": email_id}

    def create_draft(to, subject, body):
        actions.append(("create_draft", {"to": to, "subject": subject}))
        return {"status": "drafted", "draft_id": "fake-draft-id", "to": to, "subject": subject}

    return actions, {
        "get_unread_emails": get_unread_emails,
        "mark_read": mark_read,
        "delete_email": delete_email,
        "create_draft": create_draft,
    }


def _summarize_decisions(tool_calls, actions_log):
    """tool_calls: legacy/deepagents-shaped [{"tool","input","result"}, ...]
    actions_log: side-channel list from the fake tools (used only to count
    create_draft calls the way the agent actually invoked them, since
    tool_calls already carries this — kept for a cross-check, not required)."""
    decisions = {}
    drafts = []
    for call in tool_calls:
        tool = call["tool"]
        args = call["input"]
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


def _run_legacy(event):
    from agent.loop import run_agent
    start = time.time()
    result = run_agent(event)
    elapsed = time.time() - start
    return result, elapsed


def _run_deepagents(event):
    from agent_deepagents.loop import run_agent
    start = time.time()
    result = run_agent(event)
    elapsed = time.time() - start
    return result, elapsed


def compare_fixture(fixture_path: Path) -> dict:
    fixture = json.loads(fixture_path.read_text())
    fixture_emails = fixture["emails"]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_flinch_db = Path(tmpdir) / "flinch.db"
        tmp_checkpoint_db = Path(tmpdir) / "flinch_checkpoints.db"

        import roles.email_reviewer.tools as gmail_tools
        import agent_deepagents.checkpointer as checkpointer
        import agent_deepagents.approval as approval

        original_registry = dict(gmail_tools.TOOL_REGISTRY)

        legacy_actions, legacy_fakes = _fake_tools(fixture_emails)
        gmail_tools.TOOL_REGISTRY.update(legacy_fakes)

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

    legacy_decisions, legacy_drafts = _summarize_decisions(legacy_result["tool_calls"], legacy_actions)
    deepagents_decisions, deepagents_drafts = _summarize_decisions(deepagents_result["tool_calls"], [])

    all_email_ids = {e["id"] for e in fixture_emails}
    mismatches = {}
    for email_id in all_email_ids:
        l = legacy_decisions.get(email_id, "no_action")
        d = deepagents_decisions.get(email_id, "no_action")
        if l != d:
            mismatches[email_id] = {"legacy": l, "deepagents": d}

    return {
        "fixture": fixture_path.name,
        "flexible": fixture.get("flexible", False),
        "legacy_decisions": legacy_decisions,
        "deepagents_decisions": deepagents_decisions,
        "legacy_drafts": len(legacy_drafts),
        "deepagents_drafts": len(deepagents_drafts),
        "mismatches": mismatches,
        "legacy_tokens": legacy_result["tokens"],
        "deepagents_tokens": deepagents_result["tokens"],
        "legacy_seconds": round(legacy_time, 2),
        "deepagents_seconds": round(deepagents_time, 2),
    }


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    fixture_paths = sorted(FIXTURES_DIR.glob("*.json"))
    if only:
        fixture_paths = [p for p in fixture_paths if only in p.stem]

    all_reports = []
    for path in fixture_paths:
        print(f"\n=== {path.name} ===")
        report = compare_fixture(path)
        all_reports.append(report)
        print(f"  legacy:     {report['legacy_decisions']}  (+{report['legacy_drafts']} draft(s), "
              f"{report['legacy_tokens']} tokens, {report['legacy_seconds']}s)")
        print(f"  deepagents: {report['deepagents_decisions']}  (+{report['deepagents_drafts']} draft(s), "
              f"{report['deepagents_tokens']} tokens, {report['deepagents_seconds']}s)")
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
