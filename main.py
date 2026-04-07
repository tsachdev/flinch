import time
import schedule
from eventqueue.bus import init_queue, enqueue
from gateway.router import register
from agent.loop import run_agent
from memory.writer import write_session
from memory.summarizer import summarize_today

@register("support_ticket")
def handle_support_ticket(event):
    result = run_agent(event)
    write_session(result)

@register("cron")
def handle_cron(event):
    job = event["payload"].get("job")
    if job == "daily_summary":
        summarize_today()
    elif job == "email_review":
        result = run_agent(event)
        write_session(result)
    elif job == "market_watch":
        result = run_agent(event)
        write_session(result)
    elif job == "email_review_microsoft":
        result = run_agent(event)
        write_session(result)

@register("message")
def handle_message(event):
    result = run_agent(event)
    write_session(result)

@register("microsoft_email")
def handle_microsoft_email(event):
    result = run_agent(event)
    write_session(result)

@register("market_event")
def handle_market_event(event):
    job = event["payload"].get("job")
    if job == "market_watch":
        result = run_agent(event)
        write_session(result)

def start_scheduler():
    schedule.every().day.at("23:59").do(
        lambda: enqueue("cron", "scheduler", {"job": "daily_summary"})
    )
    schedule.every(2).hours.do(
        lambda: enqueue("cron", "scheduler", {"job": "email_review"})
    )
    schedule.every().day.at("08:00").do(
        lambda: enqueue("market_event", "scheduler", {"job": "market_watch"})
    )
    schedule.every(2).hours.do(
        lambda: enqueue("microsoft_email", "scheduler", {"job": "email_review_microsoft"})
    )
    print("[scheduler] daily summary at 23:59, email review every 2 hours (Gmail + Microsoft), market watch at 08:00")

if __name__ == "__main__":
    print("\n🦞 Flinch starting...\n")

    init_queue()
    start_scheduler()

    print("[main] entering main loop — Ctrl+C to stop\n")

    from gateway.router import HANDLERS
    from eventqueue.bus import dequeue, complete, fail

    while True:
        schedule.run_pending()
        event = dequeue()
        if event:
            handler = HANDLERS.get(event["type"])
            if handler:
                print(f"\n[main] routing {event['type']} → {handler.__name__}")
                try:
                    handler(event)
                    complete(event["id"])
                except Exception as e:
                    print(f"[main] error: {e}")
                    fail(event["id"])
            else:
                print(f"[main] no handler for '{event['type']}' — skipping")
                fail(event["id"])
        time.sleep(1)
