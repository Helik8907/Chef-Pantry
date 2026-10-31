"""Unit tests for extraction and chef generation pipelines with MockLLMProvider."""

import pytest
from pydantic import BaseModel

from app.domain.models import (
    CandidateMemory,
    ExtractionResult,
    Memory,
    MemoryStatus,
    MemoryType,
    RecalledMemory,
    ScoreBreakdown,
)
from app.infra.llm_client import (
    LLMError,
    LLMOutputError,
    get_llm_provider,
    reset_llm_provider,
)
from app.infra.providers.mock_llm import MockLLMProvider
from app.services.chef import Chef, ChefResponseSchema
from app.services.extraction import MemoryExtractor


def make_memory(mem_id: str, mem_type: MemoryType, text: str, structured: dict | None = None) -> Memory:
    """Helper to build a memory item using model_construct."""
    return Memory.model_construct(
        id=mem_id,
        user_id="test_user",
        type=mem_type,
        text=text,
        structured=structured or {},
        tags=[mem_type.value],
        status=MemoryStatus.ACTIVE,
        protected=(mem_type == MemoryType.ALLERGY),
        expires_at=None,
    )


def make_recalled_memory(memory: Memory) -> RecalledMemory:
    """Helper to build a recalled memory wrapper."""
    return RecalledMemory(
        memory=memory,
        score=ScoreBreakdown(similarity=0.9, recency=0.8, final_score=0.85),
        reasons=["High relevance"],
    )


# ============================================================================
# EXTRACTION PIPELINE TESTS
# ============================================================================

def test_extraction_returns_empty_when_llm_fails_twice() -> None:
    """Extraction returns empty ExtractionResult when LLMOutputError is raised twice."""
    mock_llm = MockLLMProvider()
    mock_llm.set_next_error(LLMOutputError("Malformed response"), count=2)

    extractor = MemoryExtractor(llm_provider=mock_llm)
    result = extractor.extract("I am allergic to peanuts.")

    assert isinstance(result, ExtractionResult)
    assert result.candidates == []


def test_extraction_post_processing_rules() -> None:
    """Verify confidence clamping, tag normalization, empty text dropping, and TTL defaults."""
    class CustomExtractionMock(MockLLMProvider):
        def structured_output(self, prompt: str, schema: type, system=None, temperature=None, model=None):
            return ExtractionResult(
                candidates=[
                    CandidateMemory.model_construct(
                        type=MemoryType.PREFERENCE,
                        text="   ",  # Empty after strip -> should be dropped
                        confidence=1.5,
                        tags=["TEST"],
                    ),
                    CandidateMemory.model_construct(
                        type=MemoryType.PANTRY,
                        text="Has fresh basil",
                        confidence=1.8,  # Needs clamping to 1.0
                        tags=[" Basil ", "basil", "HERBS "],
                    ),
                    CandidateMemory.model_construct(
                        type=MemoryType.TEMPORARY_CONTEXT,
                        text="Cooking for 3 guests",
                        confidence=-0.5,  # Needs clamping to 0.0
                        tags=["party"],
                    ),
                ]
            )

    extractor = MemoryExtractor(llm_provider=CustomExtractionMock())
    result = extractor.extract("I have basil and am cooking for 3 guests.")

    assert len(result.candidates) == 2

    # First valid candidate: Pantry
    pantry_cand = result.candidates[0]
    assert pantry_cand.text == "Has fresh basil"
    assert pantry_cand.confidence == 1.0
    assert pantry_cand.tags == ["basil", "herbs"]
    assert pantry_cand.is_temporary is True
    assert pantry_cand.suggested_ttl_hours == 48

    # Second valid candidate: Temporary Context
    context_cand = result.candidates[1]
    assert context_cand.text == "Cooking for 3 guests"
    assert context_cand.confidence == 0.0
    assert context_cand.tags == ["party"]
    assert context_cand.is_temporary is True
    assert context_cand.suggested_ttl_hours == 24


# ============================================================================
# CHEF GENERATION PIPELINE TESTS
# ============================================================================

def test_chef_drops_unknown_memory_ids_and_adds_attribution() -> None:
    """Chef drops unknown memory IDs and ensures the 'Because I remembered' line is present."""
    known_id = "0123456789abcdef01234561"
    unknown_id = "9999999999abcdef99999999"

    pref_mem = make_memory(known_id, MemoryType.PREFERENCE, "Likes spicy food")
    recalled = [make_recalled_memory(pref_mem)]

    class FixedMockLLM(MockLLMProvider):
        def structured_output(self, prompt: str, schema: type, system=None, temperature=None, model=None):
            return ChefResponseSchema(
                answer="Here is a spicy arrabbiata pasta recipe.",
                memory_ids_used=[known_id, unknown_id],
            )

    chef = Chef(llm_provider=FixedMockLLM())
    result = chef.generate(
        user_message="What should I make for dinner?",
        recalled=recalled,
        always_applied=[],
    )

    # Unknown ID should be dropped
    assert result.memory_ids_used == [known_id]
    assert "Because I remembered" in result.answer
    assert "Likes spicy food" in result.answer
    assert result.regenerated is False


def test_chef_passes_allergies_as_hard_constraints() -> None:
    """Chef passes allergies in always_applied as mandatory hard constraints in the prompt."""
    allergy_id = "0123456789abcdef01234562"
    allergy_mem = make_memory(allergy_id, MemoryType.ALLERGY, "Allergic to shellfish", {"allergen": "shellfish"})

    captured_prompts: list[str] = []

    class CapturingMockLLM(MockLLMProvider):
        def structured_output(self, prompt: str, schema: type, system=None, temperature=None, model=None):
            captured_prompts.append(prompt)
            return ChefResponseSchema(
                answer="Here is a vegetable risotto.",
                memory_ids_used=[],
            )

    chef = Chef(llm_provider=CapturingMockLLM())
    chef.generate(
        user_message="Surprise me with seafood!",
        recalled=[],
        always_applied=[allergy_mem],
    )

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "ACTIVE ALLERGIES AND SAVED DIETARY / FOOD PREFERENCES" in prompt
    assert allergy_id in prompt
    assert "Allergic to shellfish" in prompt


def test_chef_safety_loop_triggers_regeneration_and_succeeds() -> None:
    """Safety loop triggers regeneration when initial answer contains allergen and resolves on retry."""
    allergy_id = "0123456789abcdef01234563"
    allergy_mem = make_memory(allergy_id, MemoryType.ALLERGY, "Allergic to peanuts", {"allergen": "peanut"})

    call_count = 0

    class AlternatingMockLLM(MockLLMProvider):
        def structured_output(self, prompt: str, schema: type, system=None, temperature=None, model=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Unsafe initial output
                return ChefResponseSchema(
                    answer="Try delicious cold noodles with peanut sauce.",
                    memory_ids_used=[allergy_id],
                )
            # Safe regenerated output
            return ChefResponseSchema(
                answer="Try cold noodles with tahini sesame sauce.",
                memory_ids_used=[],
            )

    chef = Chef(llm_provider=AlternatingMockLLM())
    result = chef.generate(
        user_message="I want cold noodles.",
        recalled=[],
        always_applied=[allergy_mem],
    )

    assert call_count == 2
    assert result.regenerated is True
    assert result.safety_findings == []
    assert "sesame sauce" in result.answer
    assert "peanut" not in result.answer.lower()
    assert "Because I remembered" in result.answer


def test_chef_safety_loop_persistent_conflict_returns_safe_fallback() -> None:
    """Safety loop returns safe fallback message when regeneration still produces allergen conflict."""
    allergy_id = "0123456789abcdef01234564"
    allergy_mem = make_memory(allergy_id, MemoryType.ALLERGY, "Allergic to peanuts", {"allergen": "peanut"})

    class AlwaysUnsafeMockLLM(MockLLMProvider):
        def structured_output(self, prompt: str, schema: type, system=None, temperature=None, model=None):
            return ChefResponseSchema(
                answer="Enjoy peanut butter toast.",
                memory_ids_used=[allergy_id],
            )

    chef = Chef(llm_provider=AlwaysUnsafeMockLLM())
    result = chef.generate(
        user_message="Breakfast ideas?",
        recalled=[],
        always_applied=[allergy_mem],
    )

    assert result.regenerated is True
    assert len(result.safety_findings) > 0
    assert result.safety_findings[0].allergen == "peanut"
    # Safe fallback message warning the user
    assert "I want to make sure your food is safe" in result.answer
    assert "peanut" in result.answer.lower()
    assert "Because I remembered" in result.answer


# ============================================================================
# FACTORY & CONFIG TESTS
# ============================================================================

def test_llm_factory_mock_provider() -> None:
    """Test get_llm_provider returns MockLLMProvider when configured for mock."""
    reset_llm_provider()

    class MockSettings:
        LLM_PROVIDER = "mock"

    provider = get_llm_provider(settings=MockSettings)
    assert isinstance(provider, MockLLMProvider)
    reset_llm_provider()


def test_llm_factory_gemini_missing_key_raises_llm_error() -> None:
    """Test get_llm_provider raises readable LLMError when GEMINI_API_KEY is missing."""
    reset_llm_provider()

    class GeminiMissingKeySettings:
        LLM_PROVIDER = "gemini"
        GEMINI_API_KEY = ""

    with pytest.raises(LLMError, match="GEMINI_API_KEY is missing or empty"):
        get_llm_provider(settings=GeminiMissingKeySettings)
    reset_llm_provider()
