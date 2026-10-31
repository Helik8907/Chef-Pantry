"""Deterministic, offline mock LLM provider for tests and local development."""

import re
from typing import Any, Optional, TypeVar
from pydantic import BaseModel

from app.domain.models import CandidateMemory, ExtractionResult, MemoryType
from app.infra.llm_client import LLMOutputError, LLMProvider

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(LLMProvider):
    """Deterministic, zero-cost LLM provider running completely offline."""

    def __init__(self) -> None:
        self.raise_on_next_calls: int = 0
        self.error_to_raise: Optional[Exception] = None

    def set_next_error(self, error: Exception, count: int = 1) -> None:
        """Instruct the mock provider to raise an exception for the next `count` calls."""
        self.error_to_raise = error
        self.raise_on_next_calls = count

    def _check_injected_error(self) -> None:
        if self.raise_on_next_calls > 0:
            self.raise_on_next_calls -= 1
            err = self.error_to_raise or LLMOutputError("Simulated LLM output error.")
            raise err

    def structured_output(
        self,
        prompt: str,
        schema: type[T],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> T:
        """Return deterministic schema-valid responses based on input text patterns."""
        self._check_injected_error()

        # Handle ExtractionResult
        if issubclass(schema, ExtractionResult):
            candidates: list[CandidateMemory] = []
            prompt_lower = prompt.lower()

            # Allergy pattern
            allergy_match = re.search(r"(?:allergic to|allergy(?::|\s+to))\s+([a-zA-Z\s]+?)(?:[.,;\n]|$)", prompt, re.IGNORECASE)
            if allergy_match:
                allergen = allergy_match.group(1).strip().lower()
                candidates.append(
                    CandidateMemory(
                        type=MemoryType.ALLERGY,
                        text=f"Allergic to {allergen}",
                        structured={"allergen": allergen, "severity": "severe"},
                        tags=[allergen],
                        confidence=1.0,
                    )
                )

            # Dislike pattern
            dislike_match = re.search(r"(?:i don't like|dislike|hate)\s+([a-zA-Z\s]+?)(?:[.,;\n]|$)", prompt, re.IGNORECASE)
            if dislike_match:
                item = dislike_match.group(1).strip().lower()
                candidates.append(
                    CandidateMemory(
                        type=MemoryType.PREFERENCE,
                        text=f"Dislikes {item}",
                        structured={"kind": "dislike", "item": item},
                        tags=[item],
                        confidence=0.9,
                    )
                )

            # Like pattern
            like_match = re.search(r"(?:i like|i love|prefer)\s+([a-zA-Z\s]+?)(?:[.,;\n]|$)", prompt, re.IGNORECASE)
            if like_match and not dislike_match:
                item = like_match.group(1).strip().lower()
                candidates.append(
                    CandidateMemory(
                        type=MemoryType.PREFERENCE,
                        text=f"Likes {item}",
                        structured={"kind": "like", "item": item},
                        tags=[item],
                        confidence=0.9,
                    )
                )

            # Pantry pattern
            pantry_match = re.search(r"(?:i have|in my pantry|stocked with)\s+([a-zA-Z\s]+?)(?:[.,;\n]|$)", prompt, re.IGNORECASE)
            if pantry_match:
                item = pantry_match.group(1).strip().lower()
                candidates.append(
                    CandidateMemory(
                        type=MemoryType.PANTRY,
                        text=f"Has {item}",
                        structured={"item": item},
                        tags=[item],
                        confidence=0.85,
                        is_temporary=True,
                        suggested_ttl_hours=48,
                    )
                )

            # Meal outcome / rating pattern
            if "5 stars" in prompt_lower or "rated 5" in prompt_lower:
                candidates.append(
                    CandidateMemory(
                        type=MemoryType.MEAL_OUTCOME,
                        text="Rated previous dish 5 stars",
                        structured={"dish": "recent dish", "rating": 5, "feedback": "Delicious"},
                        tags=["rating"],
                        confidence=1.0,
                    )
                )

            # Correction pattern
            if "not vegetarian anymore" in prompt_lower or "no longer vegetarian" in prompt_lower:
                candidates.append(
                    CandidateMemory(
                        type=MemoryType.PREFERENCE,
                        text="Not vegetarian anymore",
                        structured={"kind": "diet", "item": "omnivore"},
                        tags=["diet"],
                        confidence=0.95,
                        is_correction_of_text="vegetarian diet",
                    )
                )

            return schema(candidates=candidates)  # type: ignore

        # Handle ChefResponseSchema
        if schema.__name__ == "ChefResponseSchema":
            # Extract 24-character hexadecimal IDs from prompt
            hex_ids = re.findall(r"\b[a-f0-9]{24}\b", prompt)
            # Deduplicate while preserving order
            seen = set()
            used_ids = [hid for hid in hex_ids if not (hid in seen or seen.add(hid))]

            return schema(  # type: ignore
                answer="Here is a personalized recipe tailored to your tastes: Herbed Lemon Quinoa.",
                memory_ids_used=used_ids,
            )

        # Generic fallback for any other schema
        try:
            return schema()
        except Exception:
            try:
                # Attempt with empty dict or basic defaults
                return schema.model_validate({})
            except Exception as err:
                raise LLMOutputError(f"MockLLMProvider unable to instantiate schema {schema.__name__}: {err}") from err

    def generate_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> str:
        """Return fixed-format response citing provided memories without requiring an API key."""
        self._check_injected_error()

        hex_ids = re.findall(r"\b[a-f0-9]{24}\b", prompt)
        memory_lines = [line.strip() for line in prompt.splitlines() if "[id:" in line or "Memory:" in line]

        answer = "Chef Assistant Suggestion:\n"
        if memory_lines:
            answer += "Recalled memories considered:\n"
            for ml in memory_lines[:5]:
                answer += f"- {ml}\n"
        elif hex_ids:
            answer += f"Incorporated {len(hex_ids)} user preferences.\n"
        else:
            answer += "Prepared fresh culinary guidance based on your request.\n"

        answer += "Recipe: Sautéed Seasonal Medley with aromatic herbs."
        return answer
