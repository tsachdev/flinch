from eventqueue.bus import init_queue, enqueue, dequeue, complete, peek_all

init_queue()

print("\n--- enqueuing 3 events ---")
id1 = enqueue("support_ticket", "zendesk", {"ticket_id": "4821", "subject": "Loyalty points not applied", "customer_id": "1204"})
id2 = enqueue("db_trigger",     "postgres", {"table": "orders", "row_id": "9902", "event": "insert"})
id3 = enqueue("cron",           "scheduler", {"job": "daily_summary"})

print("\n--- queue state after enqueue ---")
for row in peek_all():
    print(row)

print("\n--- dequeuing first event ---")
event = dequeue()
print(event)

print("\n--- marking it complete ---")
complete(event["id"])

print("\n--- queue state after completion ---")
for row in peek_all():
    print(row)