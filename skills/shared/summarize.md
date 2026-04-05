---
name: summarize
description: How to produce clean, structured summaries after completing a task
triggers: summary, digest, report, review, complete, done
roles: all
---

# Summarize skill

When producing a summary at the end of a session:

## Structure
Always use this order:
1. **What was found** — the raw signal (emails processed, earnings detected, tickets reviewed)
2. **What was done** — actions taken (queued, marked read, drafted, notified)
3. **What needs attention** — anything requiring human review or follow-up
4. **What was skipped and why** — items not acted on, with a one-line reason

## Rules
- Lead with numbers — "17 emails processed, 4 queued for deletion" is better than prose
- Never pad the summary — if nothing needs attention, say so in one line
- Use consistent section headers so the daily summarizer can parse them reliably
- Flag anomalies explicitly — unusual patterns belong in the summary, not buried in tool call logs
- Keep the total summary under 300 words unless the volume of items requires more
