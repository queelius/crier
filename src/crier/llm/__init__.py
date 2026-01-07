"""LLM provider module for auto-rewrite functionality.

Provides an interface for generating short-form rewrites of article content
using LLM APIs (OpenAI, Ollama, Groq, etc.).
"""

from .provider import (
    LLMProvider,
    LLMProviderError,
    RewriteResult,
    DEFAULT_REWRITE_PROMPT,
    RETRY_PROMPT_ADDITION,
)
from .openai_compat import OpenAICompatProvider

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "RewriteResult",
    "OpenAICompatProvider",
    "DEFAULT_REWRITE_PROMPT",
    "RETRY_PROMPT_ADDITION",
    "get_provider",
]


def get_provider(
    config: dict,
    *,
    temperature: float | None = None,
    model: str | None = None,
) -> LLMProvider | None:
    """Create an LLM provider from configuration.

    Args:
        config: LLM configuration dict with keys:
            - provider: Provider type ('openai' for OpenAI-compatible APIs)
            - base_url: API base URL
            - api_key: API key (optional for local providers)
            - model: Model name
            - rewrite_prompt: Optional custom prompt template
            - temperature: LLM temperature (default: 0.7)
        temperature: Override temperature (takes precedence over config).
        model: Override model name (takes precedence over config).

    Returns:
        Configured LLMProvider instance, or None if config is empty/invalid.

    Example config for Ollama:
        {
            "provider": "openai",
            "base_url": "http://localhost:11434/v1",
            "api_key": "",
            "model": "llama3"
        }

    Example config for OpenAI:
        {
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-...",
            "model": "gpt-4o-mini"
        }
    """
    if not config:
        return None

    provider_type = config.get("provider", "openai")
    base_url = config.get("base_url")
    api_key = config.get("api_key", "")
    effective_model = model if model else config.get("model")
    prompt_template = config.get("rewrite_prompt")
    effective_temp = temperature if temperature is not None else config.get("temperature", 0.7)

    if not base_url or not effective_model:
        return None

    if provider_type == "openai":
        return OpenAICompatProvider(
            base_url=base_url,
            api_key=api_key,
            model=effective_model,
            prompt_template=prompt_template,
            temperature=effective_temp,
        )

    # Unknown provider type
    return None
