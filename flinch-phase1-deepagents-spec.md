# Flinch — Phase 1 Spec: DeepAgents Migration

**Status:** Ready for autonomous development
**Owner:** Tushar Sachdev
**Repo:** `tsachdev/flinch` (main branch)
**Companion doc:** `brain-source/flinch/agent-brain-design-v1.md` (Agent Brain design — not required for Phase 1, informs Phase 2)

---

## 0. How to use this document

This spec is written to be handed to Claude Code as a standing brief for autonomous, multi-session development. It is organized as ordered milestones (M0–M6), each with an objective, tasks, the exact interfaces to extract from the current codebase before writing new code, and acceptance criteria that must pass before moving to the next milestone.

**Ground rule for whoever (human or agent) executes this:** the current source is the source of truth for interfaces, not this document. Section 5 requires reading the real files before writing anything. Do not invent function signatures, table schemas, or config keys — extract them from `main.py`, `agent/`, `eventqueue/`, `gateway/`, `memory/`, `roles/`, `ui/console.py`, and `mcp_server.py` first.

Work in a feature branch (`phase1-deepagents`) or a git worktree, never on `main` directly. Commit at the end of each milestone with a message referencing the milestone ID (e.g. `M2: email_reviewer on DeepAgents, shadow-mode diffing passes`). Open a PR (or leave the branch ready for review) at the end of M6 — do not merge to `main` without explicit human sign-off, since M6 is the production cutover.

---

## 1. Context

Flinch is a self-hosted reactive-agent platform: events (cron, inbound email, webhooks) flow through an Event Queue → Gateway → Agent Loop → Tool Layer → Memory, with role-specific Skills loaded at runtime. Four roles exist today: `email_reviewer`, `support_agent`, `personal_assistant`, `market_watcher`.

We've decided **not** to rewrite Flinch wholesale onto LangChain's DeepAgents. The reactive dispatch model (queue/gateway/cron), the flat-markdown memory system, and the SKILL.md behavior-tuning system are working, legible, and worth keeping. The piece worth replacing is the hand-rolled agent loop and provider abstraction in `agent/` — DeepAgents' checkpoint/interrupt model is a strong structural fit for the existing propose-and-approve pattern (pending email deletions, drafts, etc.), and its middleware system can replace bespoke provider-fallback code.

The console also gets rebuilt in this phase — not just repointed to a new backend, but redesigned as a modern, Cowork-style interface: what agents are running, what they did, what needs approval, and a place to tune skills in plain English. The current Flask template UI is retired, not preserved. Agent-construction UI (authoring new roles from the console) is explicitly Phase 2.

---

## 2. Scope

### In scope for Phase 1
- Replace `agent/` (agent loop + provider abstraction) with DeepAgents (`create_deep_agent` + middleware), for all four existing roles.
- Wire the new agent loop to the **existing** SQLite event queue, gateway/router, markdown memory, and SKILL.md skills system — unchanged on-disk formats.
- Replace the pending-approval mechanism's execution model with LangGraph checkpoint/interrupt, while preserving the existing `pending_queue`-style data (or its equivalent) as the durable, console-visible record.
- Rebuild the console with a modern, Cowork-style UI: a live view of which agents are running/idle, a run/session history feed per role with plain-English summaries, an approval surface for pending email actions, and a skill-tuning surface (plain-English feedback → `SKILL.md` updates). The current Flask template UI is retired, not kept for parity's sake. No task/agent-creation capability in this phase — that's Phase 2.
- Keep `mcp_server.py` working — either unchanged (if the console's HTTP API surface stays compatible) or updated in lockstep.
- Add a backend feature flag so the legacy and DeepAgents paths can run side by side during migration and be toggled without a code rollback.
- Shadow-mode / regression testing that proves behavioral parity before cutover.

### Explicitly out of scope (Phase 2)
- Building any new agent role.
- Console UI for authoring/constructing new roles (prompt, tools, model, middleware) from the console.
- Changing the reactive-pattern positioning of Flinch (still event-in, agent-out; no proactive/deliberative planning loops added).
- Webhook connector, role-authoring CLI, additional providers (Ollama, OpenAI), native macOS packaging — these stay on the existing roadmap, untouched by this phase.
- Migrating memory or skills off flat markdown into a LangGraph store. They stay as files on disk, full stop.

If work drifts into anything in the out-of-scope list, stop and flag it rather than continuing.

---

## 3. Target architecture (recap)

```
Event Sources → Event Queue (SQLite, unchanged) → Gateway/Router (unchanged)
                                                          ↓
                                          DeepAgent Loop (per role instance)
                                                          ↓
                                       Tool + Middleware Layer (checkpoint/interrupt)
                                          ↓                              ↓
                              Memory (markdown, unchanged)    Console (rebuilt, Cowork-style)
                              Skills (markdown, unchanged)    ← agent feed, approvals, skill tuning
```

Gray boxes (queue, gateway, memory, skills) do not change on-disk format or external behavior. Blue boxes (agent loop, tool/middleware) are rebuilt on DeepAgents. The console is rebuilt with a modern, agent-centric UI — scoped to observability, approvals, and skill tuning, not agent/task construction.

---

## 4. Guardrails / non-negotiables

1. **No behavioral regression.** Given the same event (same email, same market data), the DeepAgents-backed role must make the same class of decision as the legacy role (same emails queued for deletion vs. kept, same draft-worthy detection, same earnings-window logic). Exact wording of LLM-generated summaries may differ; the *decisions and tool calls* should not.
2. **Memory and skills files are untouched in format.** Anything under `memory/roles/{role}/` and `skills/roles/{role}/` must remain plain Markdown, readable with `cat`, diffable with `git diff`. DeepAgents' own filesystem/memory abstractions are not to be used as the source of truth for this data — if DeepAgents wants an in-memory or checkpoint-backed scratch space during a run, that's fine, but the durable record stays the existing markdown files, written through the existing memory module's functions (extract and reuse, don't reimplement).
3. **Feature flag, not a big-bang rewrite.** `AGENT_BACKEND=legacy|deepagents` (or equivalent name — check `config.example.py` for the existing naming convention and match it) controls which loop handles a given role. Default stays `legacy` until M6.
4. **Deployment story doesn't get heavier by default.** Use `langgraph-checkpoint-sqlite` for the checkpointer, not Postgres or LangGraph Platform, so the "$6/mo droplet, two systemd services" pitch still holds. If a future need for Postgres emerges, that's a separate decision, not a Phase 1 default.
5. **Multi-provider + fallback behavior is preserved.** Today: Anthropic (default) + Google AI Studio/Gemma-4 (alternative, free tier), with automatic fallback on provider failure. This must keep working, ideally with less custom code (LangChain's model init + a small fallback wrapper) than the current `agent/providers/` implementation.
6. **Cost/latency budget.** Token usage and wall-clock time per session (e.g., one `email_reviewer` run) should not regress by more than ~20% versus the legacy implementation. DeepAgents' planning/subagent overhead is a known risk here — measure it, don't assume it's free.

---

## 5. Preconditions — read before writing code

Before M0, read and summarize (in a scratch notes file, not this spec) the actual current interfaces:

- `main.py` — how roles are registered and the main loop is entered.
- `agent/llm.py` and `agent/providers/*` — the provider-agnostic model router and fallback logic; this is what DeepAgents' model init + middleware will replace.
- `eventqueue/` — SQLite schema, how events are enqueued/dequeued, what a pending-approval row looks like today (this schema likely does not change).
- `gateway/router.py` — how an event gets mapped to a role handler.
- `memory/` — the read/write API used by roles today (session notes, daily summaries, shared entities under `memory/shared/entities/`). Extract exact function signatures to call from the new tool layer.
- `roles/{role}/role.py`, `roles/{role}/tools.py`, `roles/{role}/__init__.py` for all four roles — the PERSONA strings and tool functions to port.
- `skills/roles/{role}/*.md` — how skill files are loaded into a role's context today.
- `ui/console.py` — current Flask routes, the dashboard/approval/session-summary/skill-feedback endpoints, and exactly what `mcp_server.py` calls on it (so the rebuilt console doesn't silently break the MCP server).
- `mcp_server.py` — the tool surface exposed to Claude Desktop (`get_email_summary`, `get_market_summary`, `get_pending_approvals`, `get_watchlist`, `approve_email`, `reject_email`, `update_skill`) and exactly which console HTTP endpoints back each one.
- `docs/adding-a-role.md` — confirms the current role contract so the DeepAgents version can honor the same contract for Phase 2 extensibility.
- `requirements.txt` / `requirements-server.txt` — current dependency set, for a clean diff of what's added.

Do not proceed to M1 until this reading pass is done and a short interface summary exists (even a throwaway `NOTES.md` in the branch is fine).

---

## 6. Work packages

### M0 — Scaffolding and feature flag
**Objective:** Get the repo ready to hold two agent-loop implementations side by side without breaking the running system.

Tasks:
- Add `deepagents`, `langgraph`, `langgraph-checkpoint-sqlite`, `langchain-anthropic`, `langchain-google-genai` to `requirements.txt` (or a new `requirements-deepagents.txt` if you want to keep the legacy install lean — decide based on how `requirements-server.txt` is currently split).
- Add the `AGENT_BACKEND` config flag to `config.example.py`, defaulting to `legacy`.
- Create `agent_deepagents/` as a new module (sibling to `agent/`), empty scaffold for now: `__init__.py`, `loop.py`, `providers.py`, `checkpointer.py`.
- Add a dispatch point in the code path that currently calls into `agent/` (found during M-minus-1 reading pass) so it branches on `AGENT_BACKEND`.

Acceptance criteria:
- `AGENT_BACKEND=legacy python main.py` runs exactly as before (no behavior change) — confirm by running the existing `tests/` suite plus one manual smoke run.
- `AGENT_BACKEND=deepagents python main.py` starts without crashing, even though no role is migrated yet (it can no-op or log "not yet implemented" for now).

---

### M1 — Provider/model abstraction on LangChain
**Objective:** Replace `agent/providers/*` fallback logic with LangChain model init, without yet touching any role's agent loop.

Tasks:
- In `agent_deepagents/providers.py`, implement a small function `get_model(role_config) -> BaseChatModel` using `langchain-anthropic` (Claude, default) and `langchain-google-genai` (Gemma-4, alternative), with the same primary/fallback semantics as today (check `agent/providers/` for exact fallback trigger conditions — timeout, rate limit, error type — and preserve them).
- Unit test: force the primary provider to fail (mock) and confirm fallback to the secondary provider fires under the same conditions as the legacy implementation.

Acceptance criteria:
- Side-by-side unit tests (legacy `agent/providers/` vs. new `agent_deepagents/providers.py`) produce the same fallback decision for the same simulated failure scenarios.

---

### M2 — Pilot migration: `email_reviewer` on DeepAgents
**Objective:** Prove the full pattern — DeepAgent loop + existing tools + existing memory + existing skills + checkpoint-based approval — on the single most complex role before generalizing.

Tasks:
- In `agent_deepagents/loop.py`, implement `build_agent(role_name)` using `create_deep_agent`, with:
  - System prompt sourced from the existing `roles/email_reviewer/role.py` PERSONA string (reuse, don't rewrite).
  - Tools: wrap the existing functions in `roles/email_reviewer/tools.py` (Gmail/Outlook fetch, `add_to_pending_queue`, `mark_read`, `create_draft`, etc.) as DeepAgents/LangChain tools. Do not reimplement their internals — these call into Gmail/Graph APIs and the existing memory/queue modules; wrap, don't rewrite.
  - Skill loading: read `skills/roles/email_reviewer/*.md` the same way the legacy loop does, and inject into the system prompt or as a middleware-provided context block.
  - Memory: on session end, write the session note to `memory/roles/email_reviewer/sessions/` using the existing memory module's write function, in the same format as today (so the console and skill-feedback system don't need to change).
- Implement the checkpoint/interrupt approval flow (see M3 — can be built in tandem since M2 without it is only half-useful, but keep the two conceptually separate in commits).
- Build a **shadow-mode harness**: `scripts/shadow_compare.py` (or similar) that takes a captured fixture (a set of unread emails — real or synthetic, redacted of any sensitive content) and runs it through both the legacy `email_reviewer` and the new DeepAgents `email_reviewer`, then diffs the *decisions* (which emails queued for deletion, which marked read, which drafted) rather than the free-text LLM output.
- Capture 5–10 realistic fixtures (redact real email content — synthesize equivalent test data if needed) and commit them under `tests/fixtures/email_reviewer/`.

Acceptance criteria:
- Shadow comparison shows matching decisions on all committed fixtures (allow LLM wording differences, not decision differences).
- A checkpoint interrupt fires correctly when `add_to_pending_queue`-equivalent is called, and the run resumes correctly on both approve and reject.
- Killing the process mid-interrupt (simulating a droplet restart) and restarting still allows the pending approval to be resumed later — this is the key new capability checkpointing buys you, so it must be explicitly tested, not assumed.

---

### M3 — Checkpoint/interrupt approval flow (formalize)
**Objective:** Turn the approval mechanism built ad hoc in M2 into the general pattern used by every role that needs human-in-the-loop approval.

Tasks:
- Implement `agent_deepagents/checkpointer.py` using `langgraph-checkpoint-sqlite`, pointed at a DB file colocated with (or reusing) the existing event-queue SQLite database — check whether reuse or a separate file is cleaner given the existing schema, and document the decision.
- Define the interrupt payload schema (what data is available to the console when a run is paused: role, action type, subject/content preview, task ID) and confirm it maps cleanly onto the existing `pending_queue` row shape used by the console today, so the console rebuild (M5) doesn't need a second data model.
- Implement resume-on-approve and resume-on-reject as thin wrappers the console (and `mcp_server.py`'s `approve_email`/`reject_email` tools) can call.

Acceptance criteria:
- A pending approval created by any of the four roles (once migrated) round-trips through pause → console/API decision → resume, with the correct tool call executing afterward (e.g., actual deletion after approval).
- Process-restart durability test (from M2) passes for every role, not just `email_reviewer`.

---

### M4 — Migrate remaining roles
**Objective:** Generalize the M2 pattern to `support_agent`, `personal_assistant`, `market_watcher`.

Tasks:
- Repeat the M2 pattern per role: system prompt from existing `role.py`, tools wrapped from existing `tools.py`, skills loaded from existing `skills/roles/{role}/`, memory written through the existing memory module.
- `market_watcher` has no approval step today (it just sends a summary) — confirm it doesn't need the checkpoint/interrupt machinery, and keep its DeepAgents loop simpler accordingly (don't add approval gating that didn't exist before).
- Build shadow-mode fixtures for each role (earnings-calendar scenarios for `market_watcher`, sample tickets for `support_agent`, sample messages for `personal_assistant`) and run the same diff-based comparison as M2.

Acceptance criteria:
- All four roles pass shadow-mode comparison against their legacy counterparts.
- Full `tests/` suite (legacy + new) passes with `AGENT_BACKEND=deepagents`.

---

### M5 — Console rebuild (modern, Cowork-style UI)
**Objective:** Replace the current Flask console's UI, not just its backend wiring, with an agent-centric interface in the spirit of Cowork: what's running, what happened, what needs approval, and a place to tune skills in plain English. The current template-based UI is explicitly being retired as outdated, not preserved for parity. No task/agent-creation UI in this phase.

Tasks:
- Build a new frontend — a lightweight SPA is recommended (React or similar), served by a thin API layer (Flask or FastAPI is fine as the API backend; the current server-rendered templates should not carry forward as-is). Core surfaces:
  - **Agent overview** — one card per role (`email_reviewer`, `support_agent`, `personal_assistant`, `market_watcher`) showing current status (idle / running now), last run time, next scheduled trigger, and a one-line summary of the most recent session.
  - **Run/session feed** — reverse-chronological history per role (and optionally a combined cross-role feed), each entry showing the plain-English session summary already generated today, expandable to the underlying tool calls for anyone who wants the detail.
  - **Approvals** — pending items (email deletions, drafts, etc.) as actionable cards, not a raw table: approve / reject / defer, with bulk selection, backed by the checkpoint/interrupt flow from M3.
  - **Skill tuning** — a per-role panel where feedback is typed in plain English ("stop deleting Nextdoor digests automatically, just mark them read") and the system rewrites the corresponding `SKILL.md` — same underlying mechanism as today, presented as a conversational input rather than a form field.
  - **Explicitly excluded:** any "new agent," "new role," or "create task" affordance. If a design naturally implies one (e.g. an empty state inviting you to add an agent), leave it out entirely or stub it as visibly disabled/"Phase 2" rather than wiring it up.
- Keep the nightly digest email and timezone display behavior from the current console.
- Re-verify the Mac menu bar app (`ui/menubar.py`, SSH tunnel) still connects to whatever host/port the new UI serves on.
- Confirm `mcp_server.py`'s calls still resolve against the new API, updating its endpoint calls if routes changed — but the **seven MCP tool names and their input/output contracts must not change**, since that's a Claude Desktop-facing interface independent of what the console looks like.

Acceptance criteria:
- Someone who has never seen the old console can, without instruction, tell which agents are running, see what each did in its last few runs, approve/reject a pending item, and submit a skill-tuning note — all from the new UI.
- No control anywhere in the new UI creates a new agent, role, or task.
- All seven MCP tools (`get_email_summary`, `get_market_summary`, `get_pending_approvals`, `get_watchlist`, `approve_email`, `reject_email`, `update_skill`) tested manually from Claude Desktop against the rebuilt console's API.
- Old Flask console is fully retired once the new UI is verified — no need to run them in parallel, since the UI itself holds no state that needs to stay in sync (unlike the agent-loop migration in M2–M4).

---

### M6 — Cutover
**Objective:** Make DeepAgents the default backend, with legacy kept as an explicit rollback path for one release cycle.

Tasks:
- Flip `AGENT_BACKEND` default to `deepagents` in `config.example.py`.
- Update `docs/deployment.md` if the systemd service definitions, dependencies, or startup sequence changed.
- Update the README's "Tech stack" and "Architecture" sections to reflect DeepAgents/LangGraph in the stack.
- Leave `agent/` (legacy) and `AGENT_BACKEND=legacy` fully functional and documented as the rollback path — do not delete legacy code in this phase.
- Tag a release (e.g., `v0.5.0-deepagents`) so rollback has a clean reference point.

Acceptance criteria:
- Fresh clone + `setup.sh` + default config runs on DeepAgents backend out of the box.
- Rollback tested: `AGENT_BACKEND=legacy` still runs correctly on the same fresh clone.

---

## 7. Testing strategy

- **Unit tests** for every wrapped tool function and the provider/fallback logic (M1), extending the existing `tests/` suite rather than starting a parallel one.
- **Shadow-mode comparison** (M2, M4) is the primary correctness gate — decisions, not prose, are what's diffed. Fixtures must be committed so the comparison is reproducible in CI or by Claude Code re-running it in a later session.
- **Checkpoint durability tests**: kill-and-resume the process mid-interrupt, for every role that has an approval step. This is the single highest-risk new behavior in this migration and deserves explicit, repeatable tests, not a one-off manual check.
- **Regression suite**: the full existing `tests/` directory must pass under both `AGENT_BACKEND=legacy` and `AGENT_BACKEND=deepagents` before M6.
- **Cost/latency measurement**: log token counts and wall-clock duration per session for both backends during M2–M4 shadow runs; flag if DeepAgents exceeds the legacy implementation by more than ~20% (guardrail #6).

---

## 8. User acceptance testing checklist (manual — Tushar)

Run through this after each relevant milestone, not just at the end:

- [ ] **After M2:** Trigger `email_reviewer` manually with `AGENT_BACKEND=deepagents` against a real (or realistic test) inbox. Confirm the pending-approval list in the console matches what you'd expect from the legacy behavior.
- [ ] **After M2/M3:** Approve one pending deletion and confirm the email is actually deleted (not just marked in the DB). Reject one and confirm it's kept. Restart the Flinch process while an approval is still pending and confirm it's still there and resumable after restart.
- [ ] **After M4:** Let all four roles run for a few real trigger cycles (a day or two) in shadow mode — `AGENT_BACKEND=legacy` still driving production, `deepagents` running in parallel logging its own decisions without acting — and spot-check that the two agree.
- [ ] **After M5:** Open the new console and confirm you can see, without hunting: which agents are running/idle, a run feed with summaries per role, pending approvals as actionable cards, and a skill-tuning input per role. Approve one item and reject another from the new UI. Submit one skill-feedback edit in plain English and confirm the corresponding `SKILL.md` file updates correctly. Confirm there is no control anywhere that creates a new agent or task.
- [ ] **After M5:** From Claude Desktop, ask "any pending approvals?" and "what's in my watchlist?" and confirm the MCP tools still return correct live data.
- [ ] **After M6:** Do a real cutover on the droplet (or a staging droplet first, if you want an extra safety margin) and monitor for 48–72 hours before considering Phase 1 fully done. Confirm the nightly digest email still arrives and looks right.

---

## 9. Rollback plan

At every milestone through M6, `AGENT_BACKEND=legacy` must remain a working, tested path. If anything in production looks wrong after cutover (M6), the rollback is a one-line config change plus a service restart — not a code revert. Legacy code (`agent/`) should not be deleted until at least one full release cycle after cutover has passed without issues, and only on explicit sign-off.

---

## 10. Definition of done for Phase 1

- All four existing roles run on DeepAgents by default, with shadow-mode-verified behavioral parity against the legacy implementation.
- Memory and skills remain flat Markdown, unchanged in format, written through the same paths as before.
- Approvals flow through LangGraph checkpoint/interrupt, durable across process restarts.
- Console is rebuilt with a modern, Cowork-style UI — agent activity, run history/summaries, approvals, and skill tuning are all clearly surfaced; the old Flask template UI is retired. No task/agent-creation capability exists yet. All seven MCP tools work unchanged from Claude Desktop's perspective.
- Legacy backend remains available via feature flag as a tested rollback path.
- No new agent roles were added, and no agent-construction UI was built — those stay in Phase 2.

---

## 11. Phase 2 preview (do not build now — for context only)

Phase 2 adds agent/task construction to the console built in Phase 1 — authoring a new role's prompt, tools, model choice, and middleware stack from the same UI, rather than editing files by hand. Because Phase 1 already delivers the modern, Cowork-style frontend, Phase 2 is additive (new screens/flows on an existing UI) rather than a second UI rewrite. This is intentionally sequenced so Phase 1 stays a scoped, verifiable infrastructure-plus-UI migration, and the higher-risk "let the console author new agents" capability lands separately once the foundation is proven.
