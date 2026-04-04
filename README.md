# 🦞 Flinch

**An open-source implementation of the Reactive agentic pattern.**

Flinch is a lightweight, self-hosted platform for running role-aware AI agents that respond to events. Something happens in the world — an email arrives, an inventory update fires, a message comes in — and the right agent acts. No deliberation, no human in the loop unless you design one in.

This is Pattern 1 of [the eight AI application patterns](https://ctoloayer.substack.com) — the Reactive pattern. The highest-volume pattern in the global economy, and the one most ripe for AI execution.

---

## What it does

Flinch runs multiple AI agent roles simultaneously from a single deployment. Each role has its own system prompt, tool access, memory, and skills. Events enter a central queue, the gateway routes them to the right role, and the agent loop executes.

Four reference roles are included out of the box:

| Role | Trigger | What it does |
|---|---|---|
| `email_reviewer` | Cron (every 2 hours) | Triages Gmail — queues deletions for approval, marks updates read, drafts replies for action items |
| `support_agent` | Inbound ticket event | Handles customer support tickets, looks up history, sends notifications |
| `store_concierge` | Inventory event | Notifies customers when watched items come back in stock |
| `personal_assistant` | Inbound message | Responds to personal messages with context from shared memory |

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

## Gmail integration (optional)

Flinch includes a working Gmail integration for the `email_reviewer` role. To enable it:

1. Create a Google Cloud project and enable the Gmail API
2. Download your OAuth credentials as `credentials.json` into the project root
3. Run `python gmail_auth.py` and complete the browser auth flow
4. A `token.json` will be saved — the email reviewer will use it automatically

See `docs/gmail-setup.md` for the full walkthrough.

---

## Console UI

Flinch includes a web console for monitoring agent activity and approving pending actions.

```bash
python ui/console.py
# → http://localhost:5001
```

Five tabs: Overview, Support, Store, Email, Assistant — each with a Summary and Actions sub-tab. Human-in-the-loop gates (e.g. email deletions) surface here for approval before execution.

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
- **Anthropic Claude** — agent intelligence (configurable model per role)
- **SQLite** — event queue and pending actions store
- **Flask** — web console
- **Schedule** — cron-based triggers
- **Gmail API** — email integration
- **Rumps** — macOS menu bar app

---

## Project structure

```
flinch/
├── agent/          # Agent loop, context builder, skills loader
├── eventqueue/     # SQLite-backed event bus
├── gateway/        # Event router
├── memory/         # Role-scoped and shared entity memory
├── roles/          # Reference role implementations
├── skills/         # SKILL.md files per role and shared
├── ui/             # Console, menu bar app
├── main.py         # Entry point
├── config.example.py
└── setup.sh
```

---

## Roadmap

- [ ] Webhook connector (receive external HTTP events)
- [ ] Slack connector
- [ ] Multi-model support per role (swap Claude for other providers)
- [ ] Role authoring CLI (`flinch new-role`)
- [ ] Docker deployment option

---

## License

MIT — see [LICENSE](LICENSE)

---

## Background

Flinch was built as a concrete implementation of the Reactive agentic pattern — one of [eight fundamental patterns](https://ctolayer.substack.com) through which AI is disrupting both SaaS and professional services. The Reactive pattern is the simplest: the world changes, the agent acts. It is also the most common pattern in the global economy today.

If you find this useful, follow along with the full pattern series.
