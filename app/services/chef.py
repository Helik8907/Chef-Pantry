"""Chef service for synthesizing personalized culinary answers with safety guardrails."""

import logging
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import Memory, MemoryType, RecalledMemory
from app.domain.safety import SafetyFinding, check_allergen_conflicts
from app.infra import config
from app.infra.llm_client import LLMProvider

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(filename: str, custom_path: Optional[Path | str] = None) -> str:
    path = Path(custom_path) if custom_path else PROMPTS_DIR / filename
    return path.read_text(encoding="utf-8")


class ChefResponseSchema(BaseModel):
    """Structured response schema returned by LLM generation."""
    model_config = ConfigDict(populate_by_name=True)

    answer: str = Field(..., description="Culinary suggestions and guidance.")
    memory_ids_used: list[str] = Field(default_factory=list, description="IDs of memories referenced.")


class ChefResult(BaseModel):
    """Container for the synthesized assistant response and audit metadata."""
    model_config = ConfigDict(populate_by_name=True)

    answer: str = Field(..., description="Final assistant response text presented to user.")
    memory_ids_used: list[str] = Field(default_factory=list, description="Validated memory IDs cited.")
    safety_findings: list[SafetyFinding] = Field(default_factory=list, description="Allergen findings if detected.")
    regenerated: bool = Field(default=False, description="Whether safety regeneration was performed.")


class Chef:
    """Home-cooking assistant service synthesizing answers with memory attribution and safety checks."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        answer_prompt_path: Optional[Path | str] = None,
        safety_prompt_path: Optional[Path | str] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.answer_prompt_template = _load_prompt("chef_answer.txt", answer_prompt_path)
        self.safety_prompt_template = _load_prompt("safety_regenerate.txt", safety_prompt_path)
        self.temperature = (
            temperature if temperature is not None else getattr(config, "LLM_TEMPERATURE_CHEF", 0.7)
        )
        self.model = model or getattr(config, "GEMINI_MODEL_CHEF", "gemini-2.5-flash")

    def _format_always_applied(self, always_applied: list[Memory]) -> str:
        if not always_applied:
            return "(No hard constraints registered)"
        lines: list[str] = []
        for mem in always_applied:
            lines.append(f"- [id: {mem.id}] (ALLERGY) {mem.text}")
        return "\n".join(lines)

    def _format_recalled_memories(self, recalled: list[RecalledMemory]) -> str:
        if not recalled:
            return "(No additional memories recalled)"
        grouped: dict[str, list[str]] = {}
        for rm in recalled:
            m = rm.memory
            m_type = m.type.value if hasattr(m.type, "value") else str(m.type)
            grouped.setdefault(m_type, []).append(f"- [id: {m.id}] {m.text}")

        sections: list[str] = []
        for group_name, items in grouped.items():
            sections.append(f"[{group_name.upper()}]\n" + "\n".join(items))
        return "\n\n".join(sections)

    def _format_conversation_history(self, history: Optional[list[tuple[str, str]]]) -> str:
        if not history:
            return "(No previous turns)"
        turns: list[str] = []
        for role, text in history:
            turns.append(f"{role.capitalize()}: {text}")
        return "\n".join(turns)

    def _append_attribution(self, answer: str, used_ids: list[str], valid_id_map: dict[str, Memory]) -> str:
        """Ensure a short 'Because I remembered...' line is included in the answer."""
        if "Because I remembered" in answer:
            return answer

        if used_ids:
            recalled_phrases = [valid_id_map[uid].text for uid in used_ids if uid in valid_id_map]
            attribution_text = "; ".join(recalled_phrases[:3])
            attribution_line = f"\n\nBecause I remembered: {attribution_text}."
        else:
            attribution_line = "\n\nBecause I remembered: your cooking preferences and dietary constraints."

        return answer.strip() + attribution_line

    def generate(
        self,
        user_message: str,
        recalled: list[RecalledMemory],
        always_applied: list[Memory],
        chat_history: Optional[list[tuple[str, str]]] = None,
    ) -> ChefResult:
        """Generate response with memory integration and allergen safety verification."""
        # Build mapping of valid memory IDs
        valid_id_map: dict[str, Memory] = {m.id: m for m in always_applied}
        for rm in recalled:
            valid_id_map[rm.memory.id] = rm.memory

        # Collect active allergies for safety checking
        active_allergies: list[Memory] = [
            m for m in always_applied if m.type == MemoryType.ALLERGY
        ] + [
            rm.memory for rm in recalled if rm.memory.type == MemoryType.ALLERGY
        ]
        # Deduplicate active allergies by id
        unique_allergies: dict[str, Memory] = {m.id: m for m in active_allergies}
        active_allergies_list = list(unique_allergies.values())

        formatted_always = self._format_always_applied(always_applied)
        formatted_recalled = self._format_recalled_memories(recalled)
        formatted_history = self._format_conversation_history(chat_history)

        prompt = self.answer_prompt_template.format(
            always_applied=formatted_always,
            recalled_memories=formatted_recalled,
            conversation_history=formatted_history,
            user_message=user_message,
        )

        response = self.llm_provider.structured_output(
            prompt=prompt,
            schema=ChefResponseSchema,
            temperature=self.temperature,
            model=self.model,
        )

        # Validate returned IDs against provided IDs
        validated_used_ids = [mid for mid in response.memory_ids_used if mid in valid_id_map]

        # First safety check
        initial_findings = check_allergen_conflicts(response.answer, active_allergies_list)

        if not initial_findings:
            final_answer = self._append_attribution(response.answer, validated_used_ids, valid_id_map)
            return ChefResult(
                answer=final_answer,
                memory_ids_used=validated_used_ids,
                safety_findings=[],
                regenerated=False,
            )

        # Regeneration loop
        logger.warning(
            "Detected %d allergen conflict(s) in initial generation. Triggering safety regeneration.",
            len(initial_findings),
        )
        conflicts_str = ", ".join(f"{f.allergen} (found '{f.matched_term}')" for f in initial_findings)

        regen_prompt = self.safety_prompt_template.format(
            allergen_conflicts=conflicts_str,
            previous_answer=response.answer,
            always_applied=formatted_always,
            recalled_memories=formatted_recalled,
            user_message=user_message,
        )

        regen_response = self.llm_provider.structured_output(
            prompt=regen_prompt,
            schema=ChefResponseSchema,
            temperature=self.temperature,
            model=self.model,
        )

        regen_used_ids = [mid for mid in regen_response.memory_ids_used if mid in valid_id_map]
        second_findings = check_allergen_conflicts(regen_response.answer, active_allergies_list)

        if second_findings:
            logger.error("Persistent allergen conflict after regeneration; returning safe fallback response.")
            conflict_names = ", ".join(sorted(list(set(f.allergen for f in second_findings))))
            fallback_answer = (
                f"I want to make sure your food is safe: I noticed an ingredient conflicting with your "
                f"recorded allergy ({conflict_names}). I could not find a completely safe alternative recipe "
                f"with the current ingredients. Please prepare a meal strictly omitting these allergens, "
                f"or let me know alternative ingredients you would like to cook with."
            )
            fallback_answer = self._append_attribution(fallback_answer, regen_used_ids, valid_id_map)
            return ChefResult(
                answer=fallback_answer,
                memory_ids_used=regen_used_ids,
                safety_findings=second_findings,
                regenerated=True,
            )

        # Regeneration succeeded cleanly
        final_regen_answer = self._append_attribution(regen_response.answer, regen_used_ids, valid_id_map)
        return ChefResult(
            answer=final_regen_answer,
            memory_ids_used=regen_used_ids,
            safety_findings=[],
            regenerated=True,
        )
