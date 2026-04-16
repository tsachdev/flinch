from config import ROLE_PROVIDERS

_clients = {}

def _get_client(provider):
    if provider not in _clients:
        if provider == "anthropic":
            from agent.providers.anthropic import create_client
            _clients[provider] = create_client()
        elif provider == "google":
            from agent.providers.google import create_client
            _clients[provider] = create_client()
        else:
            raise ValueError(f"Unknown provider: {provider}")
    return _clients[provider]

def chat(role, system, messages, tools):
    provider   = ROLE_PROVIDERS.get(role["name"], ROLE_PROVIDERS.get("default", "anthropic"))
    model      = role.get("model") or _default_model(provider)
    max_tokens = role.get("max_tokens", 1024)
    client     = _get_client(provider)

    print(f"  [llm] provider: {provider}, model: {model}")

    if provider == "anthropic":
        from agent.providers.anthropic import chat as anthropic_chat
        return anthropic_chat(client, model, max_tokens, system, messages, tools)
    elif provider == "google":
        from agent.providers.google import chat as google_chat
        return google_chat(client, model, max_tokens, system, messages, tools)

def _default_model(provider):
    defaults = {
        "anthropic": "claude-haiku-4-5-20251001",
        "google":    "models/gemma-4-26b-a4b-it",
    }
    return defaults[provider]
