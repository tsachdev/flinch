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

# Model provider config
GOOGLE_API_KEY = "your-google-api-key-here"

ROLE_PROVIDERS = {
    "default":        "anthropic",
    "market_watcher": "google",   # use Gemma for market watcher
}

# Timezone for console display (e.g. "America/New_York", "Asia/Kolkata", "Europe/London")
DISPLAY_TIMEZONE = "America/New_York"
