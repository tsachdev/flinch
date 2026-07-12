"""DigitalOcean GenAI Platform (NVIDIA NIM-hosted API) provider.

DO's serverless inference is OpenAI-API-compatible, so this uses the
`openai` SDK pointed at DO's endpoint rather than a bespoke client —
same shape as agent/providers/anthropic.py, just a different wire format.
"""
import json
from openai import OpenAI
from config import DO_GENAI_API_KEY, DO_GENAI_BASE_URL

def create_client():
    return OpenAI(api_key=DO_GENAI_API_KEY, base_url=DO_GENAI_BASE_URL)

def _convert_tools(anthropic_tools):
    """Convert Anthropic tool schema to OpenAI function-calling tool schema."""
    tools = []
    for t in anthropic_tools:
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t["input_schema"],
            },
        })
    return tools

def _convert_messages(system, messages):
    """Convert the Anthropic-shaped message history agent/loop.py accumulates
    (tool_use/tool_result content blocks) to OpenAI chat message format.
    Mirrors agent/providers/google.py's approach: 'raw' in the returned
    response is the *normalized* content-block list, not an OpenAI SDK
    object, so this function can rebuild OpenAI's shape from it on every
    call rather than needing to round-trip an OpenAI-native history."""
    openai_messages = [{"role": "system", "content": system}]

    for msg in messages:
        role, content = msg["role"], msg["content"]

        if role == "user":
            if isinstance(content, str):
                openai_messages.append({"role": "user", "content": content})
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        openai_messages.append({
                            "role": "tool",
                            "tool_call_id": item["tool_use_id"],
                            "content": item["content"],
                        })
        elif role == "assistant" and isinstance(content, list):
            text_parts, tool_calls = [], []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block["input"]),
                        },
                    })
            assistant_msg = {"role": "assistant", "content": "".join(text_parts) or None}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            openai_messages.append(assistant_msg)

    return openai_messages

def chat(client, model, max_tokens, system, messages, tools):
    openai_messages = _convert_messages(system, messages)
    openai_tools = _convert_tools(tools) if tools else None

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=openai_messages,
        tools=openai_tools,
    )

    choice = response.choices[0]
    content_blocks = []

    if choice.message.content:
        content_blocks.append({"type": "text", "text": choice.message.content})

    stop_reason = "end_turn"
    if choice.message.tool_calls:
        stop_reason = "tool_use"
        for tc in choice.message.tool_calls:
            content_blocks.append({
                "type":  "tool_use",
                "id":    tc.id,
                "name":  tc.function.name,
                "input": json.loads(tc.function.arguments),
            })

    tokens = response.usage.total_tokens if response.usage else 0

    return {
        "stop_reason": stop_reason,
        "content":     content_blocks,
        "raw":         content_blocks,  # normalized — see _convert_messages docstring
        "tokens":      tokens,
    }
