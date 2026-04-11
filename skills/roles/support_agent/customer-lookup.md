---
name: customer-lookup
description: Standard procedure for looking up and verifying customer identity
triggers: customer, account, profile, loyalty, order
roles: all
---

# Customer lookup skill

When a customer is referenced in any trigger:
1. Always call get_customer() before taking any action
2. Verify the customer_id in the payload matches the order's customer_id before applying changes
3. Flag any mismatch immediately — do not proceed without ownership confirmation
4. Note loyalty tier — Gold and Platinum customers get priority handling
5. Check points_balance — a zero balance on a Gold account is a signal worth investigating
