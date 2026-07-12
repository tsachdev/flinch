from config import ROLE_PROVIDERS, ROLE_PROVIDER_FALLBACK

_clients = {}

def chat(role, system, messages, tools):
    provider   = ROLE_PROVIDERS.get(role["name"], ROLE_PROVIDERS.get("default", "anthropic"))
    model      = role.get("model") or _default_model(provider)
    max_tokens = role.get("max_tokens", 1024)

    try:
        return _call_provider(provider, model, max_tokens, system, messages, tools)
    except Exception as e:
        fallback = ROLE_PROVIDER_FALLBACK.get(provider)
        if fallback:
            print(f"  [llm] {provider} failed ({type(e).__name__}) — falling back to {fallback}")
            fallback_model = _default_model(fallback)
            return _call_provider(fallback, fallback_model, max_tokens, system, messages, tools)
        raise

def _call_provider(provider, model, max_tokens, system, messages, tools):
    client = _get_client(provider)
    print(f"  [llm] provider: {provider}, model: {model}")

    if provider == "anthropic":
        from agent.providers.anthropic import chat as anthropic_chat
        return anthropic_chat(client, model, max_tokens, system, messages, tools)
    elif provider == "nvidia":
        from agent.providers.nvidia import chat as nvidia_chat
        return nvidia_chat(client, model, max_tokens, system, messages, tools)
    else:
        raise ValueError(f"Unknown provider: {provider}")

def _get_client(provider):
    if provider not in _clients:
        if provider == "anthropic":
            from agent.providers.anthropic import create_client
            _clients[provider] = create_client()
        elif provider == "nvidia":
            from agent.providers.nvidia import create_client
            _clients[provider] = create_client()
        else:
            raise ValueError(f"Unknown provider: {provider}")
    return _clients[provider]

def _default_model(provider):
    if provider == "nvidia":
        from config import DO_GENAI_MODEL
        return DO_GENAI_MODEL
    defaults = {
        "anthropic": "claude-haiku-4-5-20251001",
    }
    return defaults[provider]
