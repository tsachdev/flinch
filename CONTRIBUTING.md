# Contributing to Flinch

Thanks for your interest in contributing. Flinch is an open-source implementation of the Reactive agentic pattern — contributions that extend the platform while staying true to that pattern are most welcome.

---

## What we're looking for

The most valuable contributions are:

- **New connectors** — event sources that feed the queue (Slack, webhooks, calendar, RSS, etc.)
- **New roles** — agent personas with real-world utility
- **New shared skills** — reusable SKILL.md files that any role can load
- **Bug fixes** — especially around the agent loop, memory writer, or queue
- **Documentation** — clearer guides, better examples, corrected errors

We're not looking for contributions that add complexity without clear utility, or that make the core architecture harder to understand. Flinch is meant to be readable.

---

## Getting started

```bash
git clone https://github.com/tsachdev/flinch.git
cd flinch
./setup.sh
```

Fill in `config.py` with your API key and run the test suite to confirm everything is working:

```bash
python -m pytest tests/ -v
```

All 32 tests should pass before you start making changes.

---

## How to add a connector

A connector is an event source — something that puts events into the queue. Flinch currently has two: a Gmail cron connector and a market data cron connector.

**Steps:**

1. Decide on a trigger type name — use snake_case (e.g. `slack_message`, `webhook_event`)
2. Add a scheduler entry or webhook receiver that calls `enqueue(trigger_type, source, payload)`
3. Add a handler in `main.py` using the `@register` decorator
4. Register the trigger → role mapping in `agent/registry.py`
5. Add a test that enqueues an event and confirms it routes correctly

**Example — adding a cron-based connector:**
```python
# In main.py — schedule the trigger
schedule.every(30).minutes.do(
    lambda: enqueue("my_event", "scheduler", {"job": "my_job"})
)

# In main.py — handle it
@register("my_event")
def handle_my_event(event):
    result = run_agent(event)
    write_session(result)
```

Keep connectors simple. They should do one thing: get data and enqueue an event. Business logic belongs in the agent role, not the connector.

---

## How to add a role

See `docs/adding-a-role.md` for the full step-by-step guide with a worked example.

The short version:

1. Create `roles/your_role_name/` with `__init__.py`, `role.py`, `tools.py`
2. Define `PERSONA` in `role.py` and `TOOLS` + `TOOL_REGISTRY` in `tools.py`
3. Register in `agent/registry.py` and add a handler in `main.py`
4. Test with a manually enqueued event

**Rules for roles:**
- Tool names in `TOOLS` and `TOOL_REGISTRY` must match exactly
- Keep the persona focused — one role, one job
- Use constraints in the persona ("always X before Y") to guide behaviour
- Add `max_tokens` to `ROLE_MAX_TOKENS` in `registry.py` if the role does heavy work

---

## How to add a skill

Skills are Markdown files that give agents additional behaviour without code changes. They live in two places:

- `skills/roles/{role_name}/` — role-specific skills, loaded only for that role
- `skills/shared/` — shared skills, available to all roles

**To add a shared skill:**
```bash
touch skills/shared/your-skill-name.md
```

**Skill format:**
```markdown
# Skill name

Brief description of when this skill applies.

## Rules
1. First rule
2. Second rule

## Example
What good execution of this skill looks like.
```

Keep skills focused on a single behaviour. A skill should be short enough to read in 30 seconds. If it's longer than a page, split it.

---

## Pull request conventions

**Branch naming:**
- `feat/your-feature-name` for new connectors, roles, or skills
- `fix/description` for bug fixes
- `docs/description` for documentation changes

**Commit messages** — use conventional commits:
```
feat: add Slack connector for inbound messages
fix: handle empty calendar response in market_watcher
docs: add webhook setup guide
test: add unit tests for summarizer
```

**Before submitting a PR:**
- Run `python -m pytest tests/ -v` — all tests must pass
- If you added a new role or connector, include at least 3 tests
- Update `docs/adding-a-role.md` or `README.md` if the contribution changes how things work
- Keep PRs focused — one feature or fix per PR

---

## Code style

- Python 3.9+ compatible
- No external dependencies without a good reason — keep `requirements.txt` lean
- Follow the patterns already in the codebase — look at how `email_reviewer` is built before writing a new role
- Print statements for observability are fine — use `[module]` prefixes e.g. `[market]`, `[memory]`
- No type annotations required but welcome

---

## Questions

Open a GitHub issue with the `question` label. If you're unsure whether a contribution fits, open an issue before writing code — it's faster for everyone.
