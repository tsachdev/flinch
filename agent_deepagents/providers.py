"""LangChain model init + fallback, replacing agent/providers/*.

Mirrors agent/llm.py's semantics: pick a provider per role (config.ROLE_PROVIDERS),
fall back to config.ROLE_PROVIDER_FALLBACK on ANY exception from the primary
provider (not scoped to timeout/rate-limit — the legacy code uses a bare
`except Exception`, so this preserves that breadth deliberately).
"""

from config import ROLE_PROVIDERS, ROLE_PROVIDER_FALLBACK

_DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "google":    "models/gemma-4-26b-a4b-it",
}


def _default_model(provider: str) -> str:
    return _DEFAULT_MODELS[provider]


def _init_chat_model(provider: str, model: str, max_tokens: int):
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        from config import ANTHROPIC_API_KEY
        return ChatAnthropic(model=model, max_tokens=max_tokens, api_key=ANTHROPIC_API_KEY)
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        from config import GOOGLE_API_KEY
        return ChatGoogleGenerativeAI(model=model, max_output_tokens=max_tokens, api_key=GOOGLE_API_KEY)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_model(role_config: dict):
    """Return a LangChain BaseChatModel for a role, with the same primary/
    fallback provider selection as agent/llm.py::chat().

    role_config is the same dict shape agent/registry.py::get_role() returns
    (needs "name", optionally "model" and "max_tokens").
    """
    role_name  = role_config["name"]
    provider   = ROLE_PROVIDERS.get(role_name, ROLE_PROVIDERS.get("default", "anthropic"))
    model      = role_config.get("model") or _default_model(provider)
    max_tokens = role_config.get("max_tokens", 1024)

    primary = _init_chat_model(provider, model, max_tokens)

    fallback_provider = ROLE_PROVIDER_FALLBACK.get(provider)
    if not fallback_provider:
        return primary

    fallback_model = _default_model(fallback_provider)
    fallback = _init_chat_model(fallback_provider, fallback_model, max_tokens)

    return primary.with_fallbacks([fallback])
