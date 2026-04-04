import base64
import csv
import email as email_lib
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
]

TOKEN_PATH = Path(__file__).parent.parent.parent / "token.json"

TOOL_REGISTRY = {}

def tool(name):
    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn
    return decorator

def _get_gmail_service():
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def _get_watchlist():
    """Read tickers from Yahoo Finance portfolio CSV export."""
    try:
        from config import MARKET_WATCHLIST_FILE
        csv_path = Path(MARKET_WATCHLIST_FILE)
    except ImportError:
        csv_path = Path(__file__).parent.parent.parent / "portfolio.csv"

    if not csv_path.exists():
        print(f"  [market] watchlist file not found: {csv_path}")
        return []

    tickers = []
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row.get("Symbol", "").strip()
            if symbol:
                tickers.append(symbol)

    print(f"  [market] loaded {len(tickers)} tickers from {csv_path.name}")
    return tickers

def _get_metrics_config():
    try:
        from config import MARKET_METRICS
        return MARKET_METRICS
    except ImportError:
        return ["pe_ratio", "ps_ratio", "analyst_target", "guidance"]

def _get_recipient():
    try:
        from config import MARKET_WATCHER_RECIPIENT
        return MARKET_WATCHER_RECIPIENT
    except ImportError:
        return None

# ── Tools ─────────────────────────────────────

@tool("get_earnings_calendar")
def get_earnings_calendar() -> dict:
    """Check the watchlist for earnings announcements in the next 2 days."""
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance not installed. Run: pip install yfinance"}

    import logging
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)

    watchlist = _get_watchlist()
    if not watchlist:
        return {"error": "No tickers found. Check your portfolio.csv file."}

    today = datetime.today().date()
    lookahead = today + timedelta(days=2)
    upcoming = []

    for ticker in watchlist:
        try:
            stock = yf.Ticker(ticker)
            cal = stock.calendar

            if cal is None:
                continue
            if hasattr(cal, 'empty') and cal.empty:
                continue
            if isinstance(cal, dict) and not cal:
                continue

            # Handle both dict and DataFrame response formats
            if isinstance(cal, dict):
                earnings_dates = cal.get("Earnings Date", [])
                if not isinstance(earnings_dates, list):
                    earnings_dates = [earnings_dates]
            else:
                if "Earnings Date" not in cal.index:
                    continue
                earnings_dates = cal.loc["Earnings Date"]
                if not hasattr(earnings_dates, '__iter__'):
                    earnings_dates = [earnings_dates]

            # Check dates against window — runs for both dict and DataFrame
            for ed in earnings_dates:
                if ed is None:
                    continue
                ed_date = ed.date() if hasattr(ed, 'date') else ed
                if today <= ed_date <= lookahead:
                    upcoming.append({
                        "ticker": ticker,
                        "earnings_date": str(ed_date),
                    })
                    break

        except Exception as e:
            print(f"  [market] could not fetch calendar for {ticker}: {e}")
            continue

    print(f"  [market] {len(upcoming)} upcoming earnings found across {len(watchlist)} watchlist tickers")
    return {
        "total_watchlist": len(watchlist),
        "upcoming_earnings": upcoming,
        "checked_window": f"{today} to {lookahead}"
    }

@tool("get_stock_metrics")
def get_stock_metrics(ticker: str) -> dict:
    """Fetch financial metrics for a given ticker."""
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance not installed. Run: pip install yfinance"}

    metrics_config = _get_metrics_config()

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        if not info or (info.get("trailingPE") is None and info.get("currentPrice") is None):
            return {"ticker": ticker, "error": "No data returned — ticker may be delisted or unsupported"}

        result = {
            "ticker": ticker,
            "company_name": info.get("longName", ticker),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "currency": info.get("currency", "USD"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        }

        if "pe_ratio" in metrics_config:
            result["pe_ratio_trailing"] = info.get("trailingPE")
            result["pe_ratio_forward"] = info.get("forwardPE")

        if "ps_ratio" in metrics_config:
            result["ps_ratio"] = info.get("priceToSalesTrailing12Months")

        if "analyst_target" in metrics_config:
            result["analyst_target_mean"] = info.get("targetMeanPrice")
            result["analyst_target_low"] = info.get("targetLowPrice")
            result["analyst_target_high"] = info.get("targetHighPrice")
            result["analyst_recommendation"] = info.get("recommendationKey")
            result["number_of_analysts"] = info.get("numberOfAnalystOpinions")

        if "guidance" in metrics_config:
            result["revenue_growth"] = info.get("revenueGrowth")
            result["earnings_growth"] = info.get("earningsGrowth")
            result["forward_eps"] = info.get("forwardEps")

        if "pb_ratio" in metrics_config:
            result["pb_ratio"] = info.get("priceToBook")

        if "market_cap" in metrics_config:
            result["market_cap"] = info.get("marketCap")

        # Always include recent earnings surprise history
        try:
            earnings_hist = stock.earnings_history
            if earnings_hist is not None and not earnings_hist.empty:
                result["recent_earnings_surprises"] = earnings_hist.tail(4).to_dict(orient="records")
        except Exception:
            pass

        print(f"  [market] fetched metrics for {ticker}")
        return result

    except Exception as e:
        return {"ticker": ticker, "error": str(e)}

@tool("send_email_summary")
def send_email_summary(subject: str, body: str) -> dict:
    """Send the earnings summary email via Gmail."""
    recipient = _get_recipient()
    if not recipient:
        return {"error": "MARKET_WATCHER_RECIPIENT not set in config.py"}

    try:
        service = _get_gmail_service()
        message = email_lib.message.EmailMessage()
        message['To'] = recipient
        message['Subject'] = subject
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()
        print(f"  [market] email sent → {sent['id']}")
        return {"status": "sent", "message_id": sent['id'], "to": recipient}
    except Exception as e:
        return {"error": str(e)}

# ── Tool schemas ──────────────────────────────

TOOLS = [
    {
        "name": "get_earnings_calendar",
        "description": "Check the Yahoo Finance watchlist CSV for earnings announcements in the next 2 days",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_stock_metrics",
        "description": "Fetch financial metrics for a stock ticker including P/E, P/S, analyst targets, and guidance",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol e.g. AAPL, NVDA"
                }
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "send_email_summary",
        "description": "Send the earnings analysis summary email to the configured recipient",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Email subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Full email body with the earnings analysis"
                }
            },
            "required": ["subject", "body"]
        }
    }
]
