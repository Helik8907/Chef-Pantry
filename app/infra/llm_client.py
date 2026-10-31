"""LLM interface, custom exceptions, and provider factory."""

from abc import ABC, abstractmethod
from typing import Any, Optional, TypeVar
from pydantic import BaseModel

from app.infra.providers.base import run_with_backoff

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base exception for all LLM errors."""
    pass


class LLMOutputError(LLMError):
    """Exception raised when structured output is invalid, malformed, or empty."""
    pass


class LLMRateLimitError(LLMError):
    """Exception raised when LLM service rate limits or exhausts quota (429)."""
    pass


class LLMProvider(ABC):
    """Abstract interface for LLM provider implementations."""

    @abstractmethod
    def structured_output(
        self,
        prompt: str,
        schema: type[T],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> T:
        """Generate structured output adhering to a Pydantic schema."""
        pass

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> str:
        """Generate unstructured text response from the model."""
        pass


_cached_llm_provider: Optional[LLMProvider] = None


def get_llm_provider(settings: Any = None) -> LLMProvider:
    """Factory returning a cached LLMProvider instance based on configuration."""
    global _cached_llm_provider
    if _cached_llm_provider is not None:
        return _cached_llm_provider

    from app.infra import config

    provider_name = (
        getattr(settings, "LLM_PROVIDER", None)
        or getattr(config, "LLM_PROVIDER", "gemini")
    ).strip().lower()

    if provider_name == "gemini":
        if settings is not None and hasattr(settings, "GEMINI_API_KEY"):
            api_key = str(getattr(settings, "GEMINI_API_KEY") or "").strip()
        else:
            api_key = getattr(config, "GEMINI_API_KEY", "").strip()

        if not api_key:
            raise LLMError(
                "GEMINI_API_KEY is missing or empty. Please set GEMINI_API_KEY in your environment "
                "or switch LLM_PROVIDER to 'mock'."
            )
        from app.infra.providers.gemini_llm import GeminiLLMProvider

        _cached_llm_provider = GeminiLLMProvider(
            api_key=api_key,
            model_extraction=getattr(settings, "GEMINI_MODEL_EXTRACTION", config.GEMINI_MODEL_EXTRACTION),
            model_chef=getattr(settings, "GEMINI_MODEL_CHEF", config.GEMINI_MODEL_CHEF),
            temperature_extraction=getattr(settings, "LLM_TEMPERATURE_EXTRACTION", config.LLM_TEMPERATURE_EXTRACTION),
            temperature_chef=getattr(settings, "LLM_TEMPERATURE_CHEF", config.LLM_TEMPERATURE_CHEF),
            max_output_tokens=getattr(settings, "LLM_MAX_OUTPUT_TOKENS", config.LLM_MAX_OUTPUT_TOKENS),
            timeout_seconds=getattr(settings, "LLM_TIMEOUT_SECONDS", config.LLM_TIMEOUT_SECONDS),
        )
    elif provider_name == "mock":
        from app.infra.providers.mock_llm import MockLLMProvider

        _cached_llm_provider = MockLLMProvider()
    else:
        raise LLMError(f"Unsupported LLM_PROVIDER '{provider_name}'. Must be 'gemini' or 'mock'.")

    return _cached_llm_provider


def reset_llm_provider() -> None:
    """Reset the singleton cached LLMProvider instance (primarily for tests)."""
    global _cached_llm_provider
    _cached_llm_provider = None
