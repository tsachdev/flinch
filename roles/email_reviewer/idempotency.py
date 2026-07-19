"""In-process guard against duplicate email actions.

Why this exists: the 2026-07-17/18 sessions show the agent calling
delete_email on the same message ID up to 6 times in succession (see the
email_reviewer memory summary: "Tool redundancy/loop detected"). Each
redundant call is another paid model round-trip. This guard makes
delete_email / mark_read / add_to_pending_queue idempotent per process:
the first call runs the real action; repeats return the recorded result
with a note, so the model gets a sane response instead of an excuse to
keep retrying.

Scope is deliberately per-process (module-level dict, no persistence):
re-trashing an already-trashed email across restarts is harmless, and the
loop being defended against happens within one long-lived process.
"""

_actioned: dict = {}


def check_and_record(action: str, email_id: str, run):
    """Run `run()` the first time (action, email_id) is seen; short-circuit
    duplicates with the recorded result plus a note. Failed results (dicts
    with an 'error' key, or raised exceptions) are not recorded, so real
    retries after failure still work."""
    key = (action, email_id)
    if key in _actioned:
        print(f"  [idempotency] duplicate {action} for {email_id[:24]} — skipped")
        return {**_actioned[key],
                "note": f"duplicate {action} call skipped — this email was already actioned; do not retry"}
    result = run()
    if isinstance(result, dict) and "error" not in result:
        _actioned[key] = result
    return result


def reset():
    """Test hook."""
    _actioned.clear()
