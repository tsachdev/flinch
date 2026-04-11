---
name: market-analysis
description: Analyse earnings and market data for portfolio watchlist
triggers: market_event, earnings, portfolio, watchlist
roles: market_watcher
---

# Market analysis skill

When checking the earnings calendar:
- Look ahead 2 days for upcoming earnings announcements
- For each company with upcoming earnings, fetch: P/E ratio, P/S ratio, analyst price target, recent guidance signals
- Compare current price to analyst target — note if significantly above or below
- Flag if the company has missed or beaten earnings in the last 2 quarters

When sending the email summary:
- Subject: "Earnings Watch — [date]"
- Lead with the most important upcoming announcement
- Keep each stock to 3-4 bullet points maximum
- End with a 7-day price movement note for each stock
- If no upcoming earnings, send a brief "nothing notable this week" summary

## Tone
Professional but concise. No fluff. Numbers first.
