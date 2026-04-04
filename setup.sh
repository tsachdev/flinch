#!/bin/bash
# ─────────────────────────────────────────────
# Flinch — setup script
# ─────────────────────────────────────────────
# Run this once after cloning the repo to get
# Flinch ready to run on your machine.
#
#   chmod +x setup.sh
#   ./setup.sh
# ─────────────────────────────────────────────

set -e

echo ""
echo "🦞 Flinch setup"
echo "─────────────────────────────────────────────"

# ── 1. Python check ───────────────────────────
echo ""
echo "→ Checking Python version..."
PYTHON=$(command -v python3 || true)
if [ -z "$PYTHON" ]; then
  echo "✗ Python 3 not found. Please install Python 3.9 or higher."
  exit 1
fi
PYTHON_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
echo "  Found Python $PYTHON_VERSION"

# ── 2. Virtual environment ────────────────────
echo ""
echo "→ Creating virtual environment..."
if [ -d "venv" ]; then
  echo "  venv/ already exists — skipping"
else
  # Use Homebrew Python on macOS to avoid package manager conflicts
  if command -v /opt/homebrew/bin/python3 &>/dev/null; then
    /opt/homebrew/bin/python3 -m venv venv
  else
    python3 -m venv venv
  fi
  echo "  ✓ venv created"
fi

# ── 3. Activate and install dependencies ─────
echo ""
echo "→ Installing dependencies..."
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "  ✓ Dependencies installed"

# ── 4. Config check ───────────────────────────
echo ""
echo "→ Checking config..."
if [ ! -f "config.py" ]; then
  echo "  config.py not found — creating from template..."
  cp config.example.py config.py
  echo "  ✓ config.py created"
  echo ""
  echo "  ⚠️  Open config.py and fill in:"
  echo "       ANTHROPIC_API_KEY  — your Anthropic API key"
  echo "       MODEL              — Claude model to use"
  echo "       SERVER_HOST        — your deployment server (if using menu bar app)"
  echo ""
  CONFIG_NEEDS_SETUP=true
else
  # Check for unfilled placeholders
  if grep -q "sk-ant-\.\.\." config.py; then
    echo "  ⚠️  ANTHROPIC_API_KEY is not set in config.py"
    CONFIG_NEEDS_SETUP=true
  else
    echo "  ✓ config.py found"
  fi
fi

# ── 5. Database init ──────────────────────────
echo ""
echo "→ Initialising database..."
if [ -f "flinch.db" ]; then
  echo "  flinch.db already exists — skipping"
else
  python3 -c "
from eventqueue.bus import init_db
init_db()
print('  ✓ flinch.db created')
"
fi

# ── 6. Gmail OAuth (optional) ─────────────────
echo ""
echo "→ Gmail integration..."
if [ -f "token.json" ]; then
  echo "  ✓ Gmail already authorised (token.json found)"
elif [ -f "credentials.json" ]; then
  echo "  credentials.json found — run the following to authorise Gmail:"
  echo ""
  echo "    python gmail_auth.py"
  echo ""
else
  echo "  ℹ  No credentials.json found — Gmail integration disabled"
  echo "     To enable it, follow the Gmail OAuth setup guide in docs/gmail-setup.md"
fi

# ── 7. Done ───────────────────────────────────
echo ""
echo "─────────────────────────────────────────────"
if [ "$CONFIG_NEEDS_SETUP" = true ]; then
  echo "⚠️  Almost ready — fill in config.py then run:"
else
  echo "✓ Setup complete. To start Flinch:"
fi
echo ""
echo "    source venv/bin/activate"
echo "    python main.py"
echo ""
