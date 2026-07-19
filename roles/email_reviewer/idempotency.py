"""Per-session safety guard for email_reviewer tool calls.

Two independent protections, both per-process (the Flinch service handles one
event at a time in a long-lived process, so "per session" == "since the last
reset_session()"):

1. Idempotency (check_and_record) — the first (action, email_id) runs for
   real; repeats return the recorded result with a "do not retry" note.
   Defends the 2026-07-17/18 same-email-deleted-6x loop.

2. Per-run action caps (guard) — a hard ceiling on how many times a
   destructive/expensive tool may run in a single session. Defends the
   2026-07-19 runaway: get_unread_emails is capped at 10/fetch, but nothing
   stopped the agent from fetching-and-purging in a loop through the whole
   inbox (77 emails trashed in one run). Caps make that physically
   impossible regardless of what the model decides to do.

Caps are configurable in config.py (all optional; defaults below):
    EMAIL_MAX_FETCHES_PER_SESSION   get_unread_emails calls   (default 3)
    EMAIL_MAX_DELETES_PER_SESSION   delete_email calls        (default 15)
    EMAIL_MAX_QUEUED_PER_SESSION    add_to_pending_queue      (default 15)
"""

_actioned: dict = {}
_counts: dict = {}

_DEFAULT_LIMITS = {
    "get_unread_emails": 3,
    "delete_email": 15,
    "add_to_pending_queue": 15,
}
_CONFIG_KEYS = {
    "get_unread_emails": "EMAIL_MAX_FETCHES_PER_SESSION",
    "delete_email": "EMAIL_MAX_DELETES_PER_SESSION",
    "add_to_pending_queue": "EMAIL_MAX_QUEUED_PER_SESSION",
}


def reset_session() -> None:
    """Clear idempotency memory and per-run counters. Call at the start of
    each agent run so limits apply per session, not per process lifetime."""
    _actioned.clear()
    _counts.clear()


# Back-compat alias (older callers/tests used reset()).
reset = reset_session


def _limit(action: str) -> int:
    import config
    key = _CONFIG_KEYS.get(action)
    if key is not None:
        return getattr(config, key, _DEFAULT_LIMITS[action])
    return _DEFAULT_LIMITS.get(action, 10**9)


def guard(action: str, run):
    """Enforce the per-session cap for `action`. Under the cap, increment and
    run. At/over the cap, DON'T run — return a stop message the model can act
    on. Only successful runs count toward the cap (failures don't burn it)."""
    limit = _limit(action)
    if _counts.get(action, 0) >= limit:
        print(f"  [session-guard] {action} hit per-session limit ({limit}) — refusing")
        return {
            "status": "limit_reached",
            "note": (f"Per-session limit of {limit} for {action} reached. "
                     f"Stop calling this tool and end the session; the remaining "
                     f"items will be handled on the next scheduled run."),
        }
    result = run()
    if not (isinstance(result, dict) and "error" in result):
        _counts[action] = _counts.get(action, 0) + 1
    return result


def check_and_record(action: str, email_id: str, run):
    """Idempotency + per-session cap for per-email actions. Duplicate
    (action, email_id) short-circuits; otherwise the session cap applies."""
    key = (action, email_id)
    if key in _actioned:
        print(f"  [idempotency] duplicate {action} for {email_id[:24]} — skipped")
        return {**_actioned[key],
                "note": f"duplicate {action} call skipped — this email was already actioned; do not retry"}

    result = guard(action, run)
    if isinstance(result, dict) and result.get("status") not in ("limit_reached",) and "error" not in result:
        _actioned[key] = result
    return result
