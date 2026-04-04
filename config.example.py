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
