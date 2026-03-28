---
name: email-triage
description: Categorise and prioritise incoming emails
triggers: email, inbox, message, subject, unread
roles: email_reviewer
---

# Email triage skill

Categorise each email as one of:
- action-required: needs a response or decision from Tushar
- informational: useful context, no action needed
- junk: newsletters, marketing, automated notifications

For action-required emails:
1. Draft a reply that matches the sender's tone and relationship
2. Sign all replies as Tushar
3. Flag if the deadline is within 24 hours

For informational emails: mark as read, no draft needed
For junk: mark as read, no draft, no notification
