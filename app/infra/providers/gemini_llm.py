"""Google Gemini LLM provider implementation using google-genai SDK."""

import logging
from typing import Any, Optional, TypeVar
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import errors, types

from app.infra.llm_client import (
    LLMError,
    LLMOutputError,
    LLMProvider,
    LLMRateLimitError,
)
from app.infra.providers.base import run_with_backoff

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class _RetryableServerError(Exception):
    """Internal sentinel exception for transient 5xx server errors."""
    pass


class GeminiLLMProvider(LLMProvider):
    """LLM provider implementation utilizing the official Google Gemini SDK."""

    def __init__(
        self,
        api_key: str,
        model_extraction: str = "gemini-2.5-flash",
        model_chef: str = "gemini-2.5-flash",
        temperature_extraction: float = 0.1,
        temperature_chef: float = 0.7,
        max_output_tokens: int = 2048,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty.")
        self.api_key = api_key
        self.model_extraction = model_extraction
        self.model_chef = model_chef
        self.temperature_extraction = temperature_extraction
        self.temperature_chef = temperature_chef
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds

        timeout_ms = int(timeout_seconds * 1000) if timeout_seconds > 0 else None
        http_options = types.HttpOptions(timeout=timeout_ms) if timeout_ms else None
        self._client = genai.Client(api_key=self.api_key, http_options=http_options)

    @property
    def client(self) -> genai.Client:
        """Return the underlying genai.Client."""
        return self._client

    def _map_error(self, exc: Exception) -> Exception:
        """Map SDK errors to project LLM exceptions."""
        if isinstance(exc, (LLMError, _RetryableServerError)):
            return exc

        err_str = str(exc).lower()
        if isinstance(exc, errors.APIError):
            code = getattr(exc, "code", None)
            status = str(getattr(exc, "status", "")).upper()
            if code == 429 or "RESOURCE_EXHAUSTED" in status or "429" in status:
                return LLMRateLimitError(f"Gemini API rate limit exceeded: {exc}")
            if isinstance(code, int) and 500 <= code <= 599:
                return _RetryableServerError(f"Transient Gemini server error ({code}): {exc}")

        if "429" in err_str or "resource_exhausted" in err_str or "rate limit" in err_str:
            return LLMRateLimitError(f"Gemini rate limit: {exc}")
        if any(c in err_str for c in ["500", "502", "503", "504", "internal server error", "unavailable"]):
            return _RetryableServerError(f"Transient server error: {exc}")

        return LLMError(f"Gemini API failure: {exc}")

    def _execute_with_retry(self, fn: Any) -> Any:
        """Execute callable with backoff retry on rate limits and transient 5xx errors."""
        def wrapped() -> Any:
            try:
                return fn()
            except Exception as e:
                mapped = self._map_error(e)
                raise mapped from e

        try:
            return run_with_backoff(
                wrapped,
                max_attempts=3,
                base_delay=0.5,
                retryable_exceptions=(LLMRateLimitError, _RetryableServerError),
            )
        except _RetryableServerError as se:
            raise LLMError(f"Gemini server error persisted after retries: {se}") from se

    def structured_output(
        self,
        prompt: str,
        schema: type[T],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> T:
        """Generate structured output validated against a Pydantic schema."""
        target_model = model or self.model_extraction
        target_temp = temperature if temperature is not None else self.temperature_extraction
        target_max_tokens = self.max_output_tokens

        def _call_gemini(tokens_limit: int) -> Any:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=target_temp,
                max_output_tokens=tokens_limit,
                system_instruction=system,
            )
            return self._execute_with_retry(
                lambda: self._client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=config,
                )
            )

        # First attempt
        response = _call_gemini(target_max_tokens)

        # Handle known gotcha: token limit truncation can cause parsed and text to be None
        if response is None or (getattr(response, "parsed", None) is None and getattr(response, "text", None) is None):
            logger.warning("Structured output returned None. Retrying once with doubled max_output_tokens.")
            response = _call_gemini(target_max_tokens * 2)

        if response is None:
            raise LLMOutputError("Gemini returned an empty response object.")

        # Check parsed response
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            if isinstance(parsed, schema):
                return parsed
            if isinstance(parsed, dict):
                try:
                    return schema.model_validate(parsed)
                except ValidationError as err:
                    raise LLMOutputError(f"Failed to validate parsed dict into {schema.__name__}: {err}") from err

        # Fallback to text parsing
        text = getattr(response, "text", None)
        if text:
            try:
                return schema.model_validate_json(text)
            except ValidationError as err:
                raise LLMOutputError(f"Failed to parse structured JSON into {schema.__name__}: {err}") from err

        raise LLMOutputError(
            f"Failed to obtain structured output for {schema.__name__}: response was empty or hit max tokens."
        )

    def generate_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> str:
        """Generate unstructured text using Gemini."""
        target_model = model or self.model_chef
        target_temp = temperature if temperature is not None else self.temperature_chef

        config = types.GenerateContentConfig(
            temperature=target_temp,
            max_output_tokens=self.max_output_tokens,
            system_instruction=system,
        )

        response = self._execute_with_retry(
            lambda: self._client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config,
            )
        )

        text = getattr(response, "text", None)
        if text is None:
            raise LLMOutputError("Gemini returned None text response.")
        return text
