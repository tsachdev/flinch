from queue.bus import init_queue
from agent.loop import run_agent
from memory.writer import write_session

init_queue()

event = {
    "id":      "test-session-002",
    "type":    "support_ticket",
    "source":  "zendesk",
    "payload": {
        "ticket_id":   "4821",
        "subject":     "Loyalty points not applied on order #9902",
        "customer_id": "1204",
        "order_id":    "9902"
    }
}

print("--- running agent ---\n")
result = run_agent(event)

print("\n--- writing session note ---")
filepath = write_session(result)

print("\n--- session note contents ---")
print(filepath.read_text())