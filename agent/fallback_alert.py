"""Alerting for silent provider fallback.

Why this exists: on 2026-07-16 ~22:00 ET the DigitalOcean GenAI endpoint
started returning RateLimitError on every call, and the deliberately-broad
except-Exception fallback quietly routed 100% of traffic to the Anthropic
key for ~3 days (~12.7M tokens) before anyone noticed. The fallback stays
silent-by-design for transient blips; this module makes *sustained*
fallback loud by emailing after N consecutive fallbacks, throttled by a
cooldown so a dead provider doesn't also flood the inbox.

Config (all optional, read via getattr so config.py needs no changes):
    FALLBACK_ALERT_THRESHOLD       consecutive fallbacks before alerting (default 5)
    FALLBACK_ALERT_COOLDOWN_HOURS  min hours between alert emails (default 6)
    FALLBACK_ALERT_RECIPIENT       defaults to MARKET_WATCHER_RECIPIENT
"""

import base64
import email as email_lib
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import config

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
]
TOKEN_PATH = Path(__file__).parent.parent / "token.json"

_lock = threading.Lock()
_consecutive = 0
_last_alert_ts = 0.0


def _threshold() -> int:
    return getattr(config, "FALLBACK_ALERT_THRESHOLD", 5)


def _cooldown_seconds() -> float:
    return getattr(config, "FALLBACK_ALERT_COOLDOWN_HOURS", 6) * 3600


def _recipient():
    return getattr(config, "FALLBACK_ALERT_RECIPIENT",
                   getattr(config, "MARKET_WATCHER_RECIPIENT", None))


def record_success(provider: str) -> None:
    """Primary provider answered — reset the consecutive-fallback streak."""
    global _consecutive
    with _lock:
        _consecutive = 0


def record_fallback(primary: str, fallback: str, error: Exception) -> None:
    """Primary provider failed and we're about to use the fallback.

    Sends at most one alert email per cooldown window, and only once the
    streak reaches the threshold. Never raises: alerting must not break
    the agent loop it's observing.
    """
    global _consecutive, _last_alert_ts
    with _lock:
        _consecutive += 1
        streak = _consecutive
        due = (streak >= _threshold()
               and (time.time() - _last_alert_ts) >= _cooldown_seconds())
        if due:
            _last_alert_ts = time.time()
    if due:
        try:
            _send_alert(streak, primary, fallback, error)
        except Exception as e:  # noqa: BLE001 — alerting must never crash the loop
            print(f"  [fallback-alert] failed to send alert email: {e}")


def _send_alert(streak: int, primary: str, fallback: str, error: Exception) -> None:
    recipient = _recipient()
    if not recipient:
        print("  [fallback-alert] no recipient configured — skipping email")
        return

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    service = build('gmail', 'v1', credentials=creds)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    message = email_lib.message.EmailMessage()
    message['To'] = recipient
    message['Subject'] = (f"[flinch] {primary} provider failing — "
                          f"{streak} consecutive fallbacks to {fallback}")
    message.set_content(
        f"Flinch's primary LLM provider '{primary}' has failed {streak} times in a row\n"
        f"(latest error: {type(error).__name__}: {error}).\n\n"
        f"All traffic is currently falling back to '{fallback}', which bills the\n"
        f"{fallback} API key on every call. As of {now} this is still happening.\n\n"
        f"Check the primary provider's quota/billing, or switch\n"
        f"ROLE_PROVIDERS['default'] in config.py intentionally.\n\n"
        f"Next alert in {getattr(config, 'FALLBACK_ALERT_COOLDOWN_HOURS', 6)}h at the\n"
        f"earliest (FALLBACK_ALERT_COOLDOWN_HOURS); streak resets when '{primary}'\n"
        f"succeeds again.\n"
    )
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = service.users().messages().send(userId='me', body={'raw': raw}).execute()
    print(f"  [fallback-alert] alert email sent → {recipient} ({sent['id']})")
