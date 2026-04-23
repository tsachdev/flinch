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

## Post-earnings analysis (status: recent)
For tickers where earnings already happened (status = "recent"):
- Fetch stock metrics and note actual vs estimated EPS from recent_earnings_surprises
- Calculate the surprise percentage — beat or miss
- Note how the stock price has reacted (compare current price to 52-week context)
- Lead with: "BEAT" or "MISS" in bold
- Keep to 3 bullet points

## Email structure
- Section 1: "Upcoming Earnings" — companies reporting in next 2 days
- Section 2: "Recent Results" — companies that reported in last 2 days
- If both sections empty, send brief "nothing notable this week"

## Tone
Professional but concise. No fluff. Numbers first.
