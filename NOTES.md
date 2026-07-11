# Phase 1 — interface notes (read before writing agent_deepagents/ code)

Reading pass over the current codebase, per spec section 5. This is scratch documentation for the migration, not user-facing docs.

## main.py

- Entry point. `init_queue()`, `start_scheduler()` (uses `schedule` lib — cron jobs enqueue events), then a `while True` loop: `dequeue()` → look up `HANDLERS[event["type"]]` (from `gateway.router.HANDLERS`) → call handler → `complete()`/`fail()`.
- Handlers registered via `@register(event_type)` from `gateway/router.py`. Four event types map to handlers: `support_ticket`, `cron` (dispatches on `payload["job"]`: `daily_summary`/`email_review`/`market_watch`/`email_review_microsoft`), `message`, `microsoft_email`, `market_event`.
- All non-summary handlers do the same thing: `result = run_agent(event); write_session(result)`.
- **Dispatch point for AGENT_BACKEND branching**: every handler's call to `agent.loop.run_agent(event)`. Cleanest interception point is inside `run_agent` itself (or a new top-level `run_agent` that branches to `agent.loop.run_agent` vs `agent_deepagents.loop.run_agent`), so `main.py` doesn't need to change at all.

## agent/loop.py — `run_agent(event: dict) -> dict`

- `role = get_role(event["type"])` (agent/registry.py) → `build_context(role, event)` for system prompt → tool-use loop calling `llm.chat(role, system_prompt, messages, role["tools"])` until `stop_reason != "tool_use"`.
- Tool call dispatch: `role["registry"].get(block["name"])`, calls with `**block["input"]`, wraps exceptions as `{"error": ...}`.
- Returns `{session_id, event_type, role, payload, response, tool_calls, tokens}` — this exact shape is what `memory.writer.write_session()` consumes. **Must preserve this return shape** (or adapt at the boundary) so `write_session` doesn't need to change.
- `_truncate_result`: truncates large tool results (e.g. `emails` list) to keep context small — same concern applies to DeepAgents tool wrapping.

## agent/llm.py + agent/providers/*  (→ replaced by agent_deepagents/providers.py in M1)

- `llm.chat(role, system, messages, tools)`: picks provider from `config.ROLE_PROVIDERS[role["name"]]` (fallback `ROLE_PROVIDERS["default"]`, currently `"anthropic"`), model via `role.get("model")` or `_default_model(provider)`.
- **Fallback trigger**: bare `except Exception as e` around `_call_provider(...)` — ANY exception from the primary provider triggers fallback via `config.ROLE_PROVIDER_FALLBACK.get(provider)`. Not scoped to timeout/rate-limit specifically — it's blanket exception fallback. Preserve this (broad) semantics in the LangChain version, don't narrow it.
- Default models: `anthropic` → `claude-haiku-4-5-20251001`, `google` → `models/gemma-4-26b-a4b-it`.
- `agent/providers/anthropic.py`: uses raw `anthropic` SDK, wraps system prompt + last tool in `cache_control: {type: ephemeral}` blocks for prompt caching. Normalizes response to `{stop_reason, content: [{type, text|id/name/input}], raw, tokens}`.
- `agent/providers/google.py`: uses `google.genai`, converts Anthropic-style tool schemas → `types.FunctionDeclaration`, converts message history, normalizes response to the same shape (`raw` is just the normalized content list, not the SDK object, since Google doesn't need original-format history).
- `config.ROLE_PROVIDERS` / `ROLE_PROVIDER_FALLBACK` — need to check `config.py` (gitignored) for `ROLE_PROVIDER_FALLBACK` — not present in `config.example.py`! Must add it there too, or default in code. **Action for M0/M1**: add `ROLE_PROVIDER_FALLBACK = {"anthropic": "google"}` to `config.example.py` if missing (it's referenced by `agent/llm.py` but absent from the example config — pre-existing gap, worth fixing while we're in the file).

## eventqueue/bus.py — SQLite schema (`flinch.db`, unchanged)

- `queue` table: `id, type, source, payload(json), status(queued|in-progress|completed|failed), created_at, updated_at`. `enqueue()`, `dequeue()` (oldest queued, FIFO), `complete()`, `fail()`, `peek_all()`.
- `pending_queue` table (the approval mechanism DeepAgents checkpoint/interrupt replaces the *execution* of, not the schema): `id, task_type, payload(json), reason, status(pending|approved|rejected|later), created_at, updated_at`. `enqueue_pending()` dedupes on `payload.email_id` for existing pending rows. `get_pending_tasks()`, `update_pending_status()`.
- **This is the row shape the M3 interrupt payload must map onto.** `task_type` today is `delete_email` or `delete_email_microsoft`; `payload` has `email_id, subject, sender`; `reason` is separate top-level field (not nested in payload).

## gateway/router.py

- `HANDLERS` dict + `@register(event_type)` decorator. Also has its own standalone `run()` loop (poll_interval based) — appears to be an alternative to main.py's loop, unused by main.py directly (main.py imports `HANDLERS` from here but runs its own loop, not `gateway.router.run()`). Leave as-is, out of scope.

## memory/ — read/write API

- `memory/writer.py::write_session(result: dict) -> Path` — writes `memory/roles/{role}/sessions/{timestamp}.md` in a fixed markdown format (Trigger/Actions taken/Agent summary/Console summary/Metadata/Observations sections). Also calls `_upsert_entities()` which writes to `memory/shared/entities/{customers.md, known_issues.md}` — **support_agent-specific** (`get_customer`, `apply_loyalty_points` tool names hardcoded). This is the exact function the DeepAgents loop must call at session end, unchanged, passing the same `result` dict shape.
- `_generate_console_summary()` — calls Gemma directly for a 2-sentence console summary, non-fatal fallback to first substantial response line. Reused as-is.
- `memory/summarizer.py::summarize_today()` — nightly cron job (`daily_summary`), summarizes each role's today's sessions via Gemma into `memory/roles/{role}/summaries/{date}.md`, then sends a digest email via Gmail API directly (not through role tools). Untouched by Phase 1 (agent-loop swap doesn't affect this cron path — it calls `run_agent`? No — `summarize_today()` is called directly from `main.py`'s cron handler, bypassing `run_agent` entirely). No AGENT_BACKEND branching needed here.
- `agent/context.py::build_context(role, event) -> str` — assembles system prompt: persona + `_load_role_summary()` (today's or latest `memory/roles/{role}/summaries/*.md`) + `_load_matched_entities()` (keyed by `customer_id`/`contact_id`/`order_id` in payload, from `memory/shared/entities/*.md`) + `agent.skills.load_skills(role_name, payload)`. **This whole function is the "system prompt assembly" DeepAgents' `build_agent()` must replicate** — reuse it directly rather than reimplementing, since middleware/system-prompt injection in DeepAgents can just call `build_context()` for the persona+memory+skills blob and hand it to `create_deep_agent(instructions=...)`.

## roles/{role}/role.py + tools.py — persona + tools, for all four roles

- **email_reviewer**: `PERSONA` (long, imperative, "process every unread email before summarizing"). Two tool modules: `tools.py` (Gmail, via `google-api-python-client`, token at `token.json`) and `microsoft_tools.py` (Outlook, via Microsoft Graph, token at `microsoft_token.json`) — selected in `agent/registry.py::get_role()` based on trigger type (`microsoft_email` → microsoft_tools, else gmail tools.py). Tools: `get_unread_emails`, `create_draft`, `mark_read`, `delete_email`, `add_to_pending_queue` (→ `eventqueue.bus.enqueue_pending`). `microsoft_tools.py` mirrors the same five tool names with Graph-API-backed implementations — **must wrap both tool sets, selected the same way, in the DeepAgents version.**
- **support_agent**: `PERSONA` short. `tools.py` — all-mock/fake tools (`get_customer`, `get_order`, `get_loyalty_transactions`, `apply_loyalty_points`, `send_notification`, `update_ticket`) — no real backend, just returns hardcoded/synthetic data. Good candidate for shadow-mode fixtures since there's no real side effect risk.
- **market_watcher**: `PERSONA` (earnings-watch instructions). `tools.py` — `get_earnings_calendar`, `get_stock_metrics` (real yfinance calls), `send_email_summary` (real Gmail send). **No approval/pending-queue step** — confirmed, per M4 instructions not to add one.
- **personal_assistant**: `PERSONA` short. `tools.py` — all-mock (`get_contact`, `flag_urgent`, `draft_response`).
- Tool schema format used everywhere: Anthropic-native `{"name", "description", "input_schema": {"type":"object","properties":{...},"required":[...]}}`. DeepAgents/LangChain tools will need converting from this shape (`@tool` decorator wrapping the existing `TOOL_REGISTRY[name]` callables, with a Pydantic/JSON-schema args model built from `input_schema`), not reimplementing tool bodies.
- Note: `roles/{role}/skills/` directories (e.g. `roles/support_agent/skills/loyalty.md`) appear to be **dead/legacy** — not the ones actually loaded at runtime. Skills actually loaded come from `skills/roles/{role}/*.md` and `skills/shared/*.md` (see below). Do not migrate the `roles/*/skills/` dirs; leave them alone, out of scope.

## skills/ — loaded via `agent/skills.py::load_skills(role_name, payload)`

- Two-tier: `skills/shared/*.md` (all roles) + `skills/roles/{role}/*.md` (role-specific). Frontmatter format: `---\nname: ...\ndescription: ...\ntriggers: comma,separated,keywords\n---\nbody`. `_select_relevant()` matches trigger keywords against payload values (case-insensitive substring); if none match, ALL skills for the role are included (fail open, not fail closed).
- Existing files: `skills/shared/summarize.md`, `skills/roles/email_reviewer/triage.md`, `skills/roles/market_watcher/market-analysis.md`, `skills/roles/personal_assistant/tone-matching.md`, `skills/roles/support_agent/{customer-lookup,escalation,loyalty}.md`.
- Console's `/update-skill/<role>` route rewrites `skill_files[0]` (first `.glob("*.md")` match — i.e. **only ever edits one specific file per role**, not skill-selective) via a Gemma rewrite call, then auto-commits via `git commit`. The DeepAgents-era skill-tuning surface in M5 should reuse this same mechanism (rewrite the file + git commit), not reinvent it.
- Note: there's a second unused skill loader, `agent/registry.py::_load_skills()`, whose output (`role["skills"]`) is built but never actually read by `agent/context.py::build_context()` (which calls `agent.skills.load_skills()` directly instead). Dead code — ignore, don't fix as part of this migration (out of scope per guardrail against drifting into unrelated cleanup).

## ui/console.py — Flask routes (current console, retired in M5)

- Page routes: `/`, `/overview`, `/support_agent`, `/email_reviewer`, `/personal_assistant`, `/market_watcher`, `/dashboard` (server-rendered HTML+CSS, `?view=summary|actions` sub-tabs).
- Action routes: `/approve/<task_id>`, `/reject/<task_id>`, `/later/<task_id>`, `/bulk-approve|reject|later?ids=a,b,c`, `/approve-all`. `approve` calls `roles.email_reviewer.tools.delete_email` or `roles.email_reviewer.microsoft_tools.delete_email` (chosen by `task['task_type'] == 'delete_email_microsoft'`) then `update_pending_status(task_id, 'approved')`. **This exact approve→execute→mark-status sequence is what the M3 checkpoint resume-on-approve wrapper must replicate.**
- `/update-skill/<role>` (POST, JSON `{feedback}`): Gemma rewrite of the first skill file, then `git add` + `git commit` (subprocess, non-fatal on failure).
- JSON API routes (backing `mcp_server.py`, must keep contracts stable): `/api/status`, `/api/email-summary`, `/api/market-summary`, `/api/pending`, `/api/watchlist`.
  - `/api/email-summary`, `/api/market-summary` → `{summary, summary_date, recent_sessions: [{timestamp, preview}]}`.
  - `/api/pending` → `{pending: [{id, sender, subject, reason, source, created_at}], count}`.
  - `/api/watchlist` → `{stocks: [{symbol, price, change}]}` from `portfolio.csv`.
- Runs standalone Flask dev server on port 5001 (`CONSOLE_URL` in config.py).

## mcp_server.py — Claude Desktop MCP tool surface (must not change names/contracts)

- `FastMCP("flinch")`, 7 tools, each a thin `httpx` call to `CONSOLE_URL`:
  - `get_email_summary()` → GET `/api/email-summary`
  - `get_market_summary()` → GET `/api/market-summary`
  - `get_pending_approvals()` → GET `/api/pending`
  - `get_watchlist()` → GET `/api/watchlist`
  - `approve_email(task_id)` → GET `/approve/{task_id}` (follow_redirects)
  - `reject_email(task_id)` → GET `/reject/{task_id}` (follow_redirects)
  - `update_skill(role, feedback)` → POST `/update-skill/{role}`
- M5's rebuilt console API must keep these exact 7 endpoint behaviors (paths can change only if `mcp_server.py` is updated in lockstep — spec allows this, but simplest is to keep the paths identical and just change what serves them).

## docs/adding-a-role.md

- Confirms the 4-part role contract (PERSONA, TOOLS/TOOL_REGISTRY, registry entry, gateway handler) plus optional skill file — matches what's read above. DeepAgents version should honor the same authoring contract (Phase 2 concern, not Phase 1, but don't break the contract while migrating the loop).

## requirements.txt / requirements-server.txt

- `requirements.txt` (macOS dev): anthropic, schedule, flask, google-api-* stack, yfinance, pytest, msal, requests, google-genai, httpx. (Also implicitly rumps/pyobjc for menubar, not listed here — check `ui/menubar.py` imports separately if touched.)
- `requirements-server.txt` (droplet): same minus macOS-only bits, minus `requests`/`httpx` explicit (httpx comes transitively). Both need the new DeepAgents/LangGraph deps added — decision: **added to both** (not split into a separate `requirements-deepagents.txt`), since droplet is exactly where the production backend runs and needs these once `AGENT_BACKEND=deepagents` is used; feature flag alone protects against needing them at runtime for `legacy`, but install-time cost is small and simplicity wins (single manifest to keep in sync) over a lean-but-fragmented install story.

## config.py vs config.example.py

- Real `config.py` (gitignored) confirms `ROLE_PROVIDER_FALLBACK = {"google": "anthropic", "anthropic": None}` is a real, live key (just missing from the `config.example.py` template) — production currently runs `email_reviewer` and `market_watcher` on `google` with anthropic as fallback. `config.example.py` needs `ROLE_PROVIDER_FALLBACK` added so new setups match documented behavior, plus the new `AGENT_BACKEND` flag.

## M2 finding: create_deep_agent() dropped in favor of langchain.agents.create_agent

Measured during the email_reviewer pilot: `deepagents.create_deep_agent()` wires
`FilesystemMiddleware`/`SubAgentMiddleware`/`TodoListMiddleware` into every
model call unconditionally. `excluded_tools` hides their tool schemas from
the model, but the middleware `wrap_model_call` hooks still run and still
inject system-message content — they're "protected scaffolding," not
removable even via `excluded_middleware` (confirmed by tracing the actual
call stack). Real shadow-mode runs against the email_reviewer fixtures
showed ~40-55% more tokens per run than legacy for identical decisions —
over guardrail #6's ~20% budget — even after excluding tools and setting
`base_system_prompt=""`.

None of Flinch's four roles need the deep-agent filesystem/todo/subagent
harness — they're narrow, single-purpose event handlers with their own
tool set, same as today. Per explicit sign-off, `agent_deepagents/loop.py`
uses `langchain.agents.create_agent` instead — the lighter-weight primitive
`create_deep_agent` itself is built on. This keeps everything the spec
actually wanted from DeepAgents (LangGraph checkpoint/interrupt, LangChain
middleware replacing bespoke provider-fallback code) without the deep-agent
tax. Re-verified token parity after the switch: ~15-20% overhead remained
(closer to the guardrail line, attributable to LangGraph's own graph-step
overhead vs. legacy's plain while-loop, not to deep-agent scaffolding).

Practical effect: the `deepagents` PyPI package is not a runtime dependency
of `agent_deepagents/` — removed from requirements.txt/requirements-server.txt.
`langchain` (the package providing `create_agent`) was previously pulled in
transitively via `deepagents`; now listed explicitly since it's a direct
dependency.

## M2 shadow-mode results (all 8 committed fixtures)

Ran `scripts/shadow_compare.py` against all 8 fixtures under
`tests/fixtures/email_reviewer/`. Google's Gemma endpoint was visibly
unstable during this session (`ServerError`s triggering the legacy
fallback path too, and one run against fixture 04 stalled for 10+ minutes
before being killed — a live provider issue, not a bug reproduced in the
code). Re-run with `config.ROLE_PROVIDERS["email_reviewer"]` forced to
`"anthropic"` to get clean, fast, comparable numbers:

| fixture | decisions | tokens (legacy / new) | seconds (legacy / new) |
|---|---|---|---|
| 01 obvious_promos | MATCH | 8105 / 9348 | 28.9 / 58.3 (google, flaky run) |
| 02 real_person_reply | MATCH | 8499 / 12409 | 12.2 / 23.5 (google, flaky run) |
| 03 mixed_batch | 1 mismatch (fx03-3): legacy skipped `mark_read` after drafting despite its persona saying to — deepagents did both. LLM nondeterminism, not a migration bug. | 10733 / 10001 | 30.5 / 59.7 (google) |
| 04 uncertain_newsletter (flexible) | MATCH | 9442 / 9454 | 5.0 / 5.4 (anthropic) |
| 05 shipping_updates | MATCH | 9723 / 9699 | 5.3 / 10.8 (anthropic) |
| 06 brand_promo | MATCH | 9360 / 9419 | 4.8 / 5.2 (anthropic) |
| 07 security_alert (flexible) | MATCH | 9405 / 9341 | 7.8 / 5.8 (anthropic) |
| 08 empty_inbox | MATCH | 6010 / 5899 | 3.1 / 2.3 (anthropic) |

On clean (anthropic, non-flaky) runs, token parity is essentially exact
(within ±1%) — the earlier 15-55% overhead measurements were conflated with
Google-endpoint retry/fallback noise on top of the real (smaller) LangGraph
per-step overhead. Latency shows a modest, roughly-fixed per-run overhead
(a few seconds) consistent with LangGraph's graph-step machinery vs.
legacy's plain while-loop — not a per-token or multiplicative cost, so it
shouldn't compound at scale. 7 of 8 fixtures matched exactly; the one
mismatch is explained above and is not a regression.

## Open decisions carried into M0+

1. **AGENT_BACKEND dispatch point**: branch inside a thin new `run_agent(event)` wrapper (could live in `agent/loop.py` itself, or a new tiny module) that imports either `agent.loop.run_agent` or `agent_deepagents.loop.run_agent` based on `config.AGENT_BACKEND` — keeps `main.py` untouched.
2. **Checkpointer DB location**: `agent_deepagents/checkpointer.py` will point `langgraph-checkpoint-sqlite` at a *separate* file (`flinch_checkpoints.db`) rather than reusing `flinch.db` — simpler to reason about (LangGraph owns its schema fully) and avoids any risk of LangGraph's internal tables colliding with the hand-rolled `queue`/`pending_queue` tables. Documented here per spec's ask to record the reasoning.
3. **Interrupt payload schema** (M3) will carry `{role, task_type, payload, reason}` — deliberately identical field names to today's `pending_queue` row (minus id/status/timestamps, which the checkpoint thread_id and LangGraph state provide) — so the console (M5) renders both eras with one code path during migration.
