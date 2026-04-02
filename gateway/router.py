import time
from eventqueue.bus import init_queue, dequeue, complete, fail

HANDLERS = {}

def register(event_type: str):
    def decorator(fn):
        HANDLERS[event_type] = fn
        print(f"[gateway] registered handler for '{event_type}'")
        return fn
    return decorator

def run(poll_interval: float = 1.0):
    init_queue()
    print(f"[gateway] running — watching for: {list(HANDLERS.keys())}")
    while True:
        event = dequeue()
        if event:
            handler = HANDLERS.get(event["type"])
            if handler:
                print(f"[gateway] routing {event['type']} → {handler.__name__}")
                try:
                    handler(event)
                    complete(event["id"])
                except Exception as e:
                    print(f"[gateway] error in {handler.__name__}: {e}")
                    fail(event["id"])
            else:
                print(f"[gateway] no handler for '{event['type']}' — skipping")
                fail(event["id"])
        time.sleep(poll_interval)