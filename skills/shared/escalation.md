---
name: escalation
description: When and how to escalate issues to engineering or human review
triggers: error, failure, bug, systemic, repeat, pattern, mismatch
roles: all
---

# Escalation skill

Escalate to pending_review when:
- Customer ID does not match order's customer ID
- Same issue has been seen more than once (check memory for patterns)
- A financial correction did not persist after a previous session
- Data is inconsistent across two or more tool call results

When escalating:
- Set ticket status to pending_review, not resolved
- Write detailed engineering notes — include customer_id, order_id, symptom, and what was already tried
- Always notify the customer with a holding message — never leave them without a response
- Add an observation to the session note flagging for the daily summarizer
