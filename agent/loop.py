import json
from agent.registry import get_role
from agent.context import build_context
from agent import llm

def run_agent(event: dict) -> dict:
    session_id   = event["id"]
    event_type   = event["type"]
    payload      = event["payload"]

    role = get_role(event_type)
    print(f"[agent] session {session_id[:8]} — role: {role['name']}")

    system_prompt = build_context(role, event)
    messages      = [{"role": "user", "content": _build_user_message(event_type, payload)}]
    all_tool_calls = []
    total_tokens   = 0

    while True:
        response = llm.chat(role, system_prompt, messages, role["tools"])
        total_tokens += response["tokens"]

        print(f"[agent] LLM responded — stop_reason: {response['stop_reason']}")

        if response["stop_reason"] == "tool_use":
            tool_results = []
            for block in response["content"]:
                if block["type"] == "tool_use":
                    fn = role["registry"].get(block["name"])
                    if fn:
                        print(f"  [tool] {block['name']}({block['input']})")
                        try:
                            result = fn(**block["input"])
                            print(f"  [tool] → {result}")
                        except Exception as e:
                            result = {"error": str(e)}
                            print(f"  [tool] error: {e}")
                    else:
                        result = {"error": f"unknown tool: {block['name']}"}

                    all_tool_calls.append({
                        "tool":   block["name"],
                        "input":  block["input"],
                        "result": result
                    })
                    result_json = json.dumps(result)
                    if len(result_json) > 3000:
                        # Truncate large tool results to keep context manageable
                        result_json = result_json[:3000] + '..."}'
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block["id"],
                        "content":     result_json
                    })

            messages.append({"role": "assistant", "content": response["raw"]})
            messages.append({"role": "user",      "content": tool_results})

        else:
            final_text = next(
                (b["text"] for b in response["content"] if b["type"] == "text"), ""
            )
            return {
                "session_id": session_id,
                "event_type": event_type,
                "role":       role["name"],
                "payload":    payload,
                "response":   final_text,
                "tool_calls": all_tool_calls,
                "tokens":     total_tokens
            }

def _build_user_message(event_type: str, payload: dict) -> str:
    lines = [f"Trigger type: {event_type}", "Payload:"]
    for k, v in payload.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)
