# Known systemic issues

## Loyalty points accrual failure — 2026-03-10 deploy window
- affected_orders: range #9890–#9930 (estimated)
- symptom: points_applied = false on eligible orders
- root_cause: unconfirmed — likely automation pipeline bug
- status: open — no engineering ticket filed yet
- tickets_seen: 1 (#4821)
- recommendation: if second ticket seen, escalate to engineering immediately

## Loyalty Points Accrual Failure — 2026-03-28
- symptom: points_applied = false on eligible orders
- status: open
- tickets_seen: ticket #5002 (2026-03-28)
- affected_order: 9903
- recommendation: escalate to engineering if pattern repeats
