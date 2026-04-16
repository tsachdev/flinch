import anthropic
from config import ANTHROPIC_API_KEY

def create_client():
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def chat(client, model, max_tokens, system, messages, tools):
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        tools=tools,
        messages=messages
    )

    # Normalize to common format
    content_blocks = []
    for block in response.content:
        if block.type == "text":
            content_blocks.append({
                "type": "text",
                "text": block.text
            })
        elif block.type == "tool_use":
            content_blocks.append({
                "type":  "tool_use",
                "id":    block.id,
                "name":  block.name,
                "input": block.input
            })

    return {
        "stop_reason": response.stop_reason,  # "tool_use" or "end_turn"
        "content":     content_blocks,
        "raw":         response.content,      # kept for message history
        "tokens":      response.usage.input_tokens + response.usage.output_tokens
    }
