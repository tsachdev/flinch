---
name: inventory-alert
description: Notify interested customers when new inventory arrives
triggers: inventory, stock, product, arrival, drop, restock
roles: store_concierge
---

# Inventory alert skill

When new inventory arrives:
1. Always check stock levels before sending any alerts
2. Match customers to their known sizes — never alert a customer if their size is not in stock
3. Personalise the message — use the customer's first name and reference their size explicitly
4. Include urgency only if stock is genuinely limited (under 10 units)
5. Send via SMS for store events — email for online-only drops
