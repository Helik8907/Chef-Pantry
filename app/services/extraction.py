"""Memory extraction service for identifying culinary facts from conversation."""

import logging
from pathlib import Path
from typing import Optional

from app.domain.models import CandidateMemory, ExtractionResult, MemoryType
from app.infra import config
from app.infra.llm_client import LLMOutputError, LLMProvider

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt_template(filename: str, custom_path: Optional[Path | str] = None) -> str:
    """Load prompt template text from file."""
    path = Path(custom_path) if custom_path else PROMPTS_DIR / filename
    return path.read_text(encoding="utf-8")


class MemoryExtractor:
    """Extracts structured culinary memories from incoming user messages and context."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        prompt_path: Optional[Path | str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.prompt_template = load_prompt_template("extraction.txt", prompt_path)
        self.temperature = (
            temperature if temperature is not None else getattr(config, "LLM_TEMPERATURE_EXTRACTION", 0.1)
        )
        self.model = model or config.GEMINI_MODEL

    def extract(
        self,
        user_message: str,
        recent_context: Optional[list[str]] = None,
    ) -> ExtractionResult:
        """Extract candidate memories from user message, returning empty result on failure."""
        formatted_context = "\n".join(recent_context) if recent_context else "(None)"
        prompt = self.prompt_template.format(
            user_message=user_message,
            recent_context=formatted_context,
        )

        raw_result: Optional[ExtractionResult] = None

        # Execute call with one retry on LLMOutputError; never crash chat flow
        for attempt in range(2):
            try:
                raw_result = self.llm_provider.structured_output(
                    prompt=prompt,
                    schema=ExtractionResult,
                    temperature=self.temperature,
                    model=self.model,
                )
                break
            except LLMOutputError as exc:
                logger.warning("LLMOutputError during extraction (attempt %d/2): %s", attempt + 1, exc)
                if attempt == 1:
                    logger.error("Extraction failed on retry with LLMOutputError; returning empty ExtractionResult.")
                    return ExtractionResult(candidates=[])
            except Exception as exc:
                logger.error("Unexpected error during extraction: %s; returning empty ExtractionResult.", exc)
                return ExtractionResult(candidates=[])

        if raw_result is None or not raw_result.candidates:
            return ExtractionResult(candidates=[])

        return self._post_process(raw_result)

    def _post_process(self, result: ExtractionResult) -> ExtractionResult:
        """Post-process candidate memories: clean tags, clamp confidence, apply TTL defaults."""
        cleaned_candidates: list[CandidateMemory] = []

        for candidate in result.candidates:
            # Drop candidates with empty text
            cleaned_text = candidate.text.strip()
            if not cleaned_text:
                continue

            # Clamp confidence to [0.0, 1.0]
            clamped_confidence = max(0.0, min(1.0, float(candidate.confidence)))

            # Normalize tags: lower-cased, whitespace stripped, deduplicated
            seen_tags = set()
            normalized_tags: list[str] = []
            for tag in candidate.tags:
                tag_norm = tag.strip().lower()
                if tag_norm and tag_norm not in seen_tags:
                    seen_tags.add(tag_norm)
                    normalized_tags.append(tag_norm)

            # Assign temporary flag and default suggested TTL for transient categories
            is_temporary = candidate.is_temporary
            suggested_ttl = candidate.suggested_ttl_hours

            if candidate.type == MemoryType.PANTRY:
                is_temporary = True
                if suggested_ttl is None:
                    suggested_ttl = 48
            elif candidate.type == MemoryType.TEMPORARY_CONTEXT:
                is_temporary = True
                if suggested_ttl is None:
                    suggested_ttl = 24

            cleaned_candidates.append(
                CandidateMemory(
                    type=candidate.type,
                    text=cleaned_text,
                    structured=candidate.structured,
                    tags=normalized_tags,
                    confidence=clamped_confidence,
                    is_temporary=is_temporary,
                    suggested_ttl_hours=suggested_ttl,
                    is_correction_of_text=candidate.is_correction_of_text,
                )
            )

        return ExtractionResult(candidates=cleaned_candidates)
