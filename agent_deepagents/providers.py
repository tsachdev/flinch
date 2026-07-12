"""LangChain model init + fallback, replacing agent/providers/*.

Mirrors agent/llm.py's semantics: pick a provider per role (config.ROLE_PROVIDERS),
fall back to config.ROLE_PROVIDER_FALLBACK on ANY exception from the primary
provider (not scoped to timeout/rate-limit — the legacy code uses a bare
`except Exception`, so this preserves that breadth deliberately).
"""

from langchain.agents.middleware.types import AgentMiddleware

from config import ROLE_PROVIDERS, ROLE_PROVIDER_FALLBACK

_DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
}


def _default_model(provider: str) -> str:
    if provider == "nvidia":
        from config import DO_GENAI_MODEL
        return DO_GENAI_MODEL
    return _DEFAULT_MODELS[provider]


def _init_chat_model(provider: str, model: str, max_tokens: int):
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        from config import ANTHROPIC_API_KEY
        return ChatAnthropic(model=model, max_tokens=max_tokens, api_key=ANTHROPIC_API_KEY)
    elif provider == "nvidia":
        from langchain_openai import ChatOpenAI
        from config import DO_GENAI_API_KEY, DO_GENAI_BASE_URL
        return ChatOpenAI(model=model, max_tokens=max_tokens, api_key=DO_GENAI_API_KEY, base_url=DO_GENAI_BASE_URL)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def _get_primary_and_fallback(role_config: dict):
    role_name  = role_config["name"]
    provider   = ROLE_PROVIDERS.get(role_name, ROLE_PROVIDERS.get("default", "anthropic"))
    model      = role_config.get("model") or _default_model(provider)
    max_tokens = role_config.get("max_tokens", 1024)

    primary = _init_chat_model(provider, model, max_tokens)

    fallback_provider = ROLE_PROVIDER_FALLBACK.get(provider)
    if not fallback_provider:
        return primary, None

    fallback_model = _default_model(fallback_provider)
    fallback = _init_chat_model(fallback_provider, fallback_model, max_tokens)
    return primary, fallback


def get_model(role_config: dict):
    """Return a LangChain BaseChatModel for a role, with the same primary/
    fallback provider selection as agent/llm.py::chat(), as a single runnable
    (model.with_fallbacks()) for simple, non-agentic callers.

    role_config is the same dict shape agent/registry.py::get_role() returns
    (needs "name", optionally "model" and "max_tokens").
    """
    primary, fallback = _get_primary_and_fallback(role_config)
    return primary if fallback is None else primary.with_fallbacks([fallback])


class ProviderFallbackMiddleware(AgentMiddleware):
    """Agent-middleware fallback for DeepAgents callers.

    create_deep_agent's `model=` must be a plain BaseChatModel — passing
    get_model()'s `.with_fallbacks()`-wrapped runnable breaks deepagents'
    internal model-spec resolution (it isn't a BaseChatModel subclass and
    isn't a string spec either). So agentic callers pass the *primary*
    model directly and add this middleware to get the same
    except-Exception-then-fallback behavior via LangChain's
    `wrap_model_call` hook instead.
    """

    def __init__(self, fallback_model):
        super().__init__()
        self.fallback_model = fallback_model

    def wrap_model_call(self, request, handler):
        try:
            return handler(request)
        except Exception as e:
            if self.fallback_model is None:
                raise
            print(f"  [agent_deepagents] {type(e).__name__} from primary provider — falling back")
            return handler(request.override(model=self.fallback_model))


def get_model_and_middleware(role_config: dict):
    """For DeepAgents callers: (primary_model, middleware_list) — pass
    primary as create_deep_agent(model=...) and extend its middleware list
    with the returned middleware (empty if no fallback is configured)."""
    primary, fallback = _get_primary_and_fallback(role_config)
    if fallback is None:
        return primary, []
    return primary, [ProviderFallbackMiddleware(fallback)]
