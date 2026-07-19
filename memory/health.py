"""Daily Flinch health report, parsed from the systemd journal and appended
to the nightly digest (memory/summarizer._send_digest).

Added after the 2026-07 incidents — silent provider fallback billing the
Anthropic key for 3 days, and a runaway that trashed 77 emails — so any
recurrence surfaces in the digest the *same day* instead of days later. It
reads only what Flinch already logs; no new instrumentation.
"""
import re
import subprocess


def _journal_for(day: str) -> str:
    """Return the flinch service journal for YYYY-MM-DD (system tz, which is
    UTC on the droplet), or '' if journalctl is unavailable/not permitted."""
    try:
        out = subprocess.run(
            ["journalctl", "-u", "flinch",
             "--since", f"{day} 00:00:00", "--until", f"{day} 23:59:59",
             "--no-pager"],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout or ""
    except Exception:
        return ""


def health_report(day: str, journal: str = None) -> str:
    """Short plain-text health block for `day`. Pass `journal` for testing;
    otherwise it's read from journalctl. Never raises."""
    text = journal if journal is not None else _journal_for(day)
    if not text:
        return "## Flinch Health\n(no journal available)"

    def count(pattern):
        return len(re.findall(pattern, text))

    provider_calls = {}
    for p in ("deepseek", "anthropic", "nvidia"):
        n = count(rf"\[llm\] provider: {p}\b")
        if n:
            provider_calls[p] = n

    fallbacks  = count(r"falling back")
    alerts     = count(r"fallback-alert\] alert email sent")
    fetches    = count(r"fetched \d+ unread")
    trashed    = count(r"trashed →")
    guard_hits = count(r"session-guard\]")
    maxturns   = count(r"max turns")
    completed  = count(r"queue\] completed")
    errors     = count(r"(?i)error code|credit balance|ratelimiterror")

    lines = ["## Flinch Health"]
    if provider_calls:
        lines.append("LLM calls: " + ", ".join(f"{p} {n}" for p, n in provider_calls.items()))
    lines.append(f"Runs completed: {completed}")
    lines.append(f"Email batches fetched: {fetches} · emails trashed: {trashed}")

    flags = []
    if fallbacks:
        flags.append(f"{fallbacks} provider fallback(s)"
                     + (f", {alerts} alert email(s) sent" if alerts else ""))
    if guard_hits:
        flags.append(f"per-session cap hit {guard_hits}x")
    if maxturns:
        flags.append(f"max-turns backstop hit {maxturns}x")
    if errors:
        flags.append(f"{errors} error line(s) in log")
    lines.append("Flags: " + ("; ".join(flags) if flags else "none — all clean"))

    return "\n".join(lines)
