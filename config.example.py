# ─────────────────────────────────────────────
# Flinch — configuration template
# ─────────────────────────────────────────────
# Copy this file to config.py and fill in your values.
#
#   cp config.example.py config.py
#
# config.py is gitignored and should never be committed.
# ─────────────────────────────────────────────


# Anthropic API key
# Get yours at https://console.anthropic.com/
ANTHROPIC_API_KEY = "sk-ant-..."

# Claude model to use for all agent roles
# Recommended: "claude-haiku-4-5-20251001" (fast, cost-effective)
# Alternative: "claude-sonnet-4-6" (more capable, higher cost)
MODEL = "claude-haiku-4-5-20251001"

# SSH connection string for your deployment server
# Format: "user@ip_address" or "user@hostname"
# Used by the Mac menu bar app to establish an SSH tunnel to the console UI
# Example: "root@123.456.789.000"
SERVER_HOST = "root@YOUR_SERVER_IP"

# Path to your Yahoo Finance portfolio CSV export
MARKET_WATCHLIST_FILE = "portfolio.csv"

# Metrics to include in analysis
MARKET_METRICS = ["pe_ratio", "ps_ratio", "analyst_target", "guidance"]

# Email to receive earnings summaries
MARKET_WATCHER_RECIPIENT = "youremail@email.com"

# Microsoft Graph API (for Outlook/Office 365 email)
MICROSOFT_CLIENT_ID  = "your-client-id"
MICROSOFT_TENANT_ID  = "consumers"
MICROSOFT_TOKEN_FILE = "microsoft_token.json"

# DigitalOcean GenAI Platform (NVIDIA NIM-hosted API) — primary model
# provider for all roles. Get your API key, endpoint, and model name from
# the GenAI Platform section of the DigitalOcean control panel. Serverless
# inference there is OpenAI-API-compatible (used via langchain-openai /
# the openai SDK, not a bespoke client).
DO_GENAI_API_KEY  = "your-digitalocean-genai-api-key"
DO_GENAI_BASE_URL = "https://your-do-genai-endpoint/v1"
DO_GENAI_MODEL    = "your-model-name"  # e.g. a Llama/Nemotron variant from DO's model catalog

ROLE_PROVIDERS = {
    "default": "nvidia",
}

# Fallback provider to use when a role's primary provider raises any exception
# (timeout, rate limit, auth error, etc.) — keyed by primary provider name.
# A value of None means no fallback for that provider.
ROLE_PROVIDER_FALLBACK = {
    "nvidia":    "anthropic",
    "anthropic": None,
}

# Fallback alerting (agent/fallback_alert.py) — the fallback above is silent
# by design for transient blips, but sustained fallback means every call is
# billing the fallback provider's key (see the Jul 2026 incident: primary
# rate-limited for 3 days unnoticed). After FALLBACK_ALERT_THRESHOLD
# consecutive fallbacks, an alert email is sent to FALLBACK_ALERT_RECIPIENT,
# at most once per FALLBACK_ALERT_COOLDOWN_HOURS. The streak resets whenever
# the primary succeeds. All three are optional; defaults shown.
FALLBACK_ALERT_THRESHOLD      = 5
FALLBACK_ALERT_COOLDOWN_HOURS = 6
FALLBACK_ALERT_RECIPIENT      = MARKET_WATCHER_RECIPIENT

# Agent loop backend — "deepagents" (agent_deepagents/) or "legacy" (agent/).
# Both implementations run side by side; this flag picks which one handles
# events. Cut over to "deepagents" as the default in M6 of the Phase 1
# migration (see flinch-phase1-deepagents-spec.md) — shadow-mode verified
# against legacy first (see NOTES.md). Set back to "legacy" to roll back;
# the legacy loop is kept fully functional for at least one release cycle.
AGENT_BACKEND = "deepagents"

# Timezone for console display (e.g. "America/New_York", "Asia/Kolkata", "Europe/London")
DISPLAY_TIMEZONE = "America/New_York"

CONSOLE_URL = "http://localhost:5001"  # URL for MCP server to reach the Flinch console
