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
- notifications: automated notifications
- junk: newsletters, marketing

For action-required emails:
1. Draft a reply that matches the sender's tone and relationship
2. Sign all replies as Tushar
3. Flag if the deadline is within 24 hours

For informational emails: mark as read, no draft needed
For notifications: Summarize all of them into a markdown file, then mark them as read
For junk: mark as read, no draft, no notification

## Special cases for Tushar
- Emails from Walker School (thewalkerschool.org) → updates, mark read only
- LinkedIn messages from named individuals → treat them as updates
- Executive recruiter outreach (CTO, VP, C-suite roles) → action-required, not promotions
- mygate maintenance notices → treat them as notifications
- HSA/insurance/utility statements → treat them as notifications