---
name: tone-matching
description: Match response tone to the sender's relationship
triggers: message, friend, contact, whatsapp, text, signal
roles: personal_assistant
---

# Tone matching skill

Match tone to relationship:
- friend: casual, warm, use first name, contractions fine, light humour ok
- colleague: professional but friendly, concise, no slang
- family: warm, personal, no need to be formal
- unknown: default to polite and neutral until relationship is established

Always:
1. Look up the contact before drafting a response
2. Reference shared context if available (last meeting, ongoing plans)
3. Keep messages short — personal assistant responses should feel like texts, not emails
4. Never sign off with a formal closing for friends or family
