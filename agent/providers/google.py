import json
import google.genai as genai
import google.genai.types as types
from config import GOOGLE_API_KEY

_client = None

def create_client():
    global _client
    _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client

def _convert_tools(anthropic_tools):
    """Convert Anthropic tool schema to Google function declarations."""
    declarations = []
    for t in anthropic_tools:
        declarations.append(types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t["input_schema"]
        ))
    return [types.Tool(function_declarations=declarations)]

def _convert_messages(messages):
    """Convert Anthropic message format to Google Content list."""
    history = []
    for msg in messages:
        if msg["role"] == "user":
            if isinstance(msg["content"], str):
                history.append(types.Content(
                    role="user",
                    parts=[types.Part(text=msg["content"])]
                ))
            elif isinstance(msg["content"], list):
                parts = []
                for item in msg["content"]:
                    if item.get("type") == "tool_result":
                        result_data = json.loads(item["content"])
                        parts.append(types.Part(
                            function_response=types.FunctionResponse(
                                name=item.get("tool_use_id", "unknown"),
                                response=result_data
                            )
                        ))
                if parts:
                    history.append(types.Content(role="user", parts=parts))
        elif msg["role"] == "assistant":
            if isinstance(msg["content"], list):
                parts = []
                for block in msg["content"]:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(types.Part(text=block["text"]))
                        elif block.get("type") == "tool_use":
                            parts.append(types.Part(
                                function_call=types.FunctionCall(
                                    name=block["name"],
                                    args=block["input"]
                                )
                            ))
                    else:
                        if hasattr(block, "text"):
                            parts.append(types.Part(text=block.text))
                if parts:
                    history.append(types.Content(role="model", parts=parts))
    return history

def chat(client, model, max_tokens, system, messages, tools):
    google_tools   = _convert_tools(tools)
    history        = _convert_messages(messages[:-1])  # all but last
    last_msg       = messages[-1]

    # Last user message
    if isinstance(last_msg["content"], str):
        last_parts = [types.Part(text=last_msg["content"])]
    else:
        last_parts = [types.Part(text=str(last_msg["content"]))]

    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=google_tools,
        max_output_tokens=max_tokens,
    )

    response = client.models.generate_content(
        model=model,
        contents=history + [types.Content(role="user", parts=last_parts)],
        config=config,
    )

    # Normalize to common format
    content_blocks = []
    stop_reason    = "end_turn"

    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            content_blocks.append({"type": "text", "text": part.text})
        elif hasattr(part, "function_call") and part.function_call:
            stop_reason = "tool_use"
            content_blocks.append({
                "type":  "tool_use",
                "id":    f"call_{part.function_call.name}",
                "name":  part.function_call.name,
                "input": dict(part.function_call.args)
            })

    # Token usage
    tokens = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        tokens = (response.usage_metadata.prompt_token_count or 0) + \
                 (response.usage_metadata.candidates_token_count or 0)

    return {
        "stop_reason": stop_reason,
        "content":     content_blocks,
        "raw":         content_blocks,  # Google doesn't need raw for history, we use normalized
        "tokens":      tokens
    }
