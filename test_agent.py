from queue.bus import init_queue, enqueue
from agent.loop import run_agent

init_queue()

event = {
    "id":      "test-session-001",
    "type":    "support_ticket",
    "source":  "zendesk",
    "payload": {
        "ticket_id":   "4821",
        "subject":     "Loyalty points not applied on order #9902",
        "customer_id": "1204",
        "order_id":    "9902"
    }
}

print("--- running agent on support ticket ---\n")
result = run_agent(event)

print("\n--- agent result ---")
print(f"session:  {result['session_id']}")
print(f"tokens:   {result['tokens']}")
print(f"\nresponse:\n{result['response']}")