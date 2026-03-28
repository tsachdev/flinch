---
name: loyalty-points
description: Handle missing or incorrect loyalty point disputes
triggers: loyalty, points, balance, redemption, accrual
roles: support_agent
---

# Loyalty points skill

When a customer reports missing loyalty points:
1. Verify order ownership matches the customer before applying points
2. Check payment method — gift cards are ineligible for points accrual
3. Check discount_code — some promo codes disable points accrual
4. If points_applied is false and no disqualifying factors exist, apply manually
5. If the order date is 2026-03-10, check known_issues — this is a confirmed deploy window bug
6. If this is the second loyalty ticket for the same customer, escalate to engineering immediately
