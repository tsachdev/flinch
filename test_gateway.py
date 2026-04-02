from eventqueue.bus import init_queue, enqueue
from gateway.router import register, run

init_queue()

@register("support_ticket")
def handle_support_ticket(event):
    p = event["payload"]
    print(f"  [handler] support ticket #{p['ticket_id']} — '{p['subject']}'")
    print(f"  [handler] customer: {p['customer_id']}")

@register("cron")
def handle_cron(event):
    p = event["payload"]
    print(f"  [handler] cron job fired: {p['job']}")

print("\n--- enqueuing 3 events (2 handled, 1 unhandled) ---")
enqueue("support_ticket", "zendesk",   {"ticket_id": "4821", "subject": "Loyalty points not applied", "customer_id": "1204"})
enqueue("cron",           "scheduler", {"job": "daily_summary"})
enqueue("db_trigger",     "postgres",  {"table": "orders", "row_id": "9902"})

print("\n--- starting gateway (will process queue then idle) ---\n")
run(poll_interval=0.5)