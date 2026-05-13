<img src="assets/logo.svg" width="360" alt="Flinch"/>

**An open-source implementation of the Reactive agentic pattern.**

Flinch is a lightweight, self-hosted platform for running role-aware AI agents that respond to events. Something happens in the world — an email arrives, an inventory update fires, a message comes in — and the right agent acts. No deliberation, no human in the loop unless you design one in.

This is Pattern 1 of [the eight AI application patterns](https://ctolayer.substack.com) — the Reactive pattern. The highest-volume pattern in the global economy, and the one most ripe for AI execution.

---

## What it does

Flinch runs multiple AI agent roles simultaneously from a single deployment. Each role has its own system prompt, tool access, memory, and skills. Events enter a central queue, the gateway routes them to the right role, and the agent loop executes.

Four reference roles are included out of the box:

| Role | Trigger | What it does |
|---|---|---|
| `email_reviewer` | Cron (every 2 hours) | Triages Gmail and Microsoft Outlook — queues deletions for approval, marks updates read, drafts replies for action items |
| `support_agent` | Inbound ticket event | Handles customer support tickets, looks up history, sends notifications |
| `personal_assistant` | Inbound message | Responds to personal messages with context from shared memory |
| `market_watcher` | Cron (daily 08:00) | Checks earnings calendar (±2 days) for your Yahoo Finance watchlist, fetches P/E, P/S, analyst targets, emails analysis |

---

## Architecture

```
Event Sources (Gmail, webhooks, cron, messages)
        ↓
  [ Event Queue ]       SQLite-backed, trigger-agnostic
        ↓
    [ Gateway ]         Routes events to the correct role handler
        ↓
  [ Agent Loop ]        Role-aware, long-running sessions per event
        ↓
  [ Tool Layer ]        Role-specific tools (Gmail, notifications, lookups)
        ↓
  [ Memory System ]     Role-scoped session notes + shared entity memory
        ↓
  [ Skills System ]     SKILL.md files loaded per role at runtime
```

**Memory** is hybrid: each role maintains its own session logs and daily summaries under `memory/roles/{role}/`, while shared knowledge (customers, contacts, known issues) lives in `memory/shared/entities/`.

**Skills** are plain Markdown files that tell agents how to behave in specific situations — no code changes needed to extend agent behaviour.

**Model abstraction** separates the agent loop from any specific LLM provider. Each role can run on a different model — Claude for nuanced reasoning, Gemma 4 for structured tasks. Provider fallback is built in: if the primary provider fails, Flinch automatically retries with the configured fallback.

---

## Quickstart

**Requirements:** Python 3.9+, an Anthropic API key

```bash
# 1. Clone
git clone https://github.com/tsachdev/flinch.git
cd flinch

# 2. Run setup
chmod +x setup.sh
./setup.sh

# 3. Fill in your config
cp config.example.py config.py
# Edit config.py — add your ANTHROPIC_API_KEY

# 4. Start
source venv/bin/activate
python main.py
```

You should see:

```
🦞 Flinch starting...
[scheduler] daily summary at 23:59, email review every 2 hours
[main] entering main loop — Ctrl+C to stop
```

---

## See it in action

Flinch runs three agent roles continuously from a single deployment. Here's what a typical day looks like.

**Email reviewer — every 2 hours**
```
[agent] session a3f2b1 — role: email_reviewer
[tool] get_unread_emails({})
[gmail] fetched 20 unread emails
[tool] add_to_pending_queue → 8 promotional emails queued for approval
[tool] mark_read → 9 update emails marked read
[tool] create_draft → 1 draft reply created for action-required email
[memory] session note → memory/roles/email_reviewer/sessions/2026-04-05T...md
```

**Microsoft Outlook reviewer — every 2 hours**
```
[agent] session c4d1e2 — role: email_reviewer
  [llm] provider: google, model: models/gemma-4-26b-a4b-it
  [tool] get_unread_emails({})
  [microsoft] fetched 16 unread emails
  [tool] add_to_pending_queue → 9 newsletters queued for approval
  [tool] mark_read → 5 updates marked read
  [memory] session note → memory/roles/email_reviewer/sessions/...md
```

**Market watcher — every morning at 08:00**
```
[agent] session b7c3d2 — role: market_watcher
[tool] get_earnings_calendar({})
[market] loaded 38 tickers from portfolio.csv
[market] 2 upcoming earnings found: NFLX (Apr 16), INFY (Apr 16)
[tool] get_stock_metrics → NFLX: P/E 39x, forward P/E 25x, analyst target $113 (buy)
[tool] get_stock_metrics → INFY: P/E 17x, revenue growth 3.2%, earnings growth -5.3%
[tool] send_email_summary → earnings preview sent
```

**Console — human-in-the-loop approvals**
```
Pending approvals (8)
LinkedIn Job Alerts — Executive Director role at Inside Higher Ed
→ [Delete] [Keep] [Later]
Costco Wholesale — Shop Easter Favorites!
→ [Delete] [Keep] [Later]
Office Depot — BOGO deals + Spring Clearance
→ [Delete] [Keep] [Later]
```

The full web console runs at `localhost:5001` and shows live queue activity, per-role session history, daily summaries, and pending approval queues.

---

## Gmail integration (optional)

Flinch includes a working Gmail integration for the `email_reviewer` role. To enable it:

1. Create a Google Cloud project and enable the Gmail API
2. Download your OAuth credentials as `credentials.json` into the project root
3. Run `python gmail_auth.py` and complete the browser auth flow
4. A `token.json` will be saved — the email reviewer will use it automatically

See `docs/gmail-setup.md` for the full walkthrough.

---

## Microsoft Outlook integration (optional)

Flinch includes a Microsoft Graph API connector for the `email_reviewer` role, enabling it to process Outlook and Office 365 inboxes alongside Gmail.

1. Register an app in the [Azure Portal](https://portal.azure.com) with `Mail.Read`, `Mail.ReadWrite`, `Mail.Send` delegated permissions
2. Add `MICROSOFT_CLIENT_ID` and `MICROSOFT_TENANT_ID` to `config.py`
3. Run `python microsoft_auth.py` to complete the device auth flow
4. A `microsoft_token.json` will be saved — the reviewer will process both inboxes automatically

---

## Console UI

Flinch includes a web console for monitoring agent activity and approving pending actions.

```bash
python ui/console.py
# → http://localhost:5001
```

Five tabs: Overview, Email, Support, Assistant, Market — each with a Summary and Actions sub-tab. Features include:

- **Bulk approvals** — select multiple pending emails and delete, keep, or defer in one click
- **Skill feedback** — update agent behaviour in plain English from the Email tab; Flinch rewrites the skill file automatically
- **Session summaries** — LLM-generated 2-sentence summary of what each agent did, visible at a glance
- **Timezone display** — all timestamps shown in your configured local timezone
- **Nightly digest** — daily email summarising all agent activity across roles

---

## Mac menu bar app

A lightweight menu bar app gives you one-click access to the console from macOS. It connects via SSH tunnel — no open ports required.

```bash
python ui/menubar.py
```

To auto-start on login, configure a launchd agent pointing at `ui/menubar.py`. See `docs/menubar-setup.md`.

---

## Adding a role

Flinch is designed to be extended. To add your own agent role:

1. Create a folder under `roles/your_role_name/`
2. Define `role.py` (PERSONA string), `tools.py` (tool functions), `__init__.py`
3. Register the role in `agent/registry.py`
4. Add a gateway handler in `gateway/router.py`
5. Optionally add a SKILL.md under `skills/roles/your_role_name/`

See `docs/adding-a-role.md` for a step-by-step walkthrough with a worked example.

---

## Deployment

Flinch runs comfortably on a $6/month DigitalOcean Droplet (Ubuntu 22.04). Two systemd services keep it running:

- `flinch.service` — the main agent loop
- `flinch-console.service` — the web console

See `docs/deployment.md` for the full setup guide.

---

## Tech stack

- **Python 3.9+**
- **Anthropic Claude** — default LLM provider (claude-haiku class)
- **Google AI Studio / Gemma 4** — alternative provider for structured roles (free tier)
- **SQLite** — event queue and pending actions store
- **Flask** — web console
- **Schedule** — cron-based triggers
- **Gmail API** — Gmail integration
- **Microsoft Graph API** — Outlook / Office 365 integration
- **yfinance** — market data for the market_watcher role
- **Rumps** — macOS menu bar app

---

## Project structure

```
flinch/
├── agent/
│   ├── providers/  # LLM provider implementations (Anthropic, Google)
│   ├── llm.py      # Provider-agnostic model router
│   └── ...
├── eventqueue/
├── gateway/
├── memory/
├── roles/
├── skills/
├── ui/
├── main.py
├── config.example.py
└── setup.sh
```

---

## Roadmap

- [x] Multi-model support per role (Anthropic + Google AI Studio / Gemma 4)
- [x] Microsoft Outlook connector via Graph API
- [x] Human-in-the-loop approval console with bulk actions
- [x] Skill feedback form — update agent behaviour without code changes
- [ ] Webhook connector (receive external HTTP events in real time)
- [ ] Docker deployment option
- [ ] Role authoring CLI (`flinch new-role`)
- [ ] Additional provider support (Ollama, OpenAI)

---

## License

MIT — see [LICENSE](LICENSE)

---

## Background

Flinch was built as a concrete implementation of the Reactive agentic pattern — one of [eight fundamental patterns](https://ctolayer.substack.com) through which AI is disrupting both SaaS and professional services. The Reactive pattern is the simplest: the world changes, the agent acts. It is also the most common pattern in the global economy today.

If you find this useful, follow along with the full pattern series.
