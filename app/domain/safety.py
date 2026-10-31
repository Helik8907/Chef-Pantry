"""Heuristic allergen safety checker for chef assistant responses.

DISCLAIMER:
This module provides best-effort heuristic keyword and synonym matching.
It does NOT provide certified medical safety, allergen certification, or clinical advice.
Users with severe or life-threatening allergies must always exercise their own judgment
and verify all recipe ingredients directly.
"""

import re
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import Memory, MemoryType


class SafetyFinding(BaseModel):
    """Detailed finding of a potential allergen conflict detected in assistant text."""
    model_config = ConfigDict(populate_by_name=True)

    allergen: str = Field(..., description="Canonical allergen entity associated with the user profile.")
    matched_term: str = Field(..., description="Exact word or phrase matched in the generated response.")
    reason: str = Field(..., description="Short explanation of why this term presents a potential allergen conflict.")


ALLERGEN_SYNONYMS: dict[str, list[str]] = {
    "peanut": ["peanut", "peanuts", "groundnut", "groundnuts"],
    "milk": ["milk", "dairy", "butter", "ghee", "paneer", "cheese", "cream", "yogurt", "whey", "casein", "curd"],
    "egg": ["egg", "eggs", "mayonnaise", "mayo", "albumin"],
    "tree nut": [
        "tree nut", "tree nuts", "nut", "nuts", "almond", "almonds", "walnut", "walnuts",
        "cashew", "cashews", "pistachio", "pistachios", "hazelnut", "hazelnuts", "pecan", "pecans",
        "macadamia", "macadamias", "brazil nut", "brazil nuts"
    ],
    "gluten": ["gluten", "wheat", "barley", "rye", "flour", "semolina", "spelt", "couscous"],
    "fish": ["fish", "salmon", "tuna", "cod", "tilapia", "anchovy", "anchovies", "trout", "halibut", "sardine", "sardines"],
    "shellfish": [
        "shellfish", "shrimp", "prawn", "prawns", "crab", "crabs", "lobster", "lobsters",
        "clam", "clams", "mussel", "mussels", "oyster", "oysters", "scallop", "scallops"
    ],
    "soy": ["soy", "soya", "soybean", "soybeans", "tofu", "edamame", "tempeh", "miso", "tamari"],
    "sesame": ["sesame", "sesame seed", "sesame seeds", "tahini"],
}


def _is_negated(text: str, start: int, end: int) -> bool:
    """Check whether a matched term is negated (e.g. 'peanut-free', 'without peanuts')."""
    suffix = text[end:end + 15]
    if re.match(r"^[- ]free\b", suffix, re.IGNORECASE):
        return True

    prefix = text[max(0, start - 40):start]
    negation_pattern = (
        r"\b(without|no|free from|free of|zero|avoid|avoiding|contain(?:s)? no|does not contain|doesn't contain)\s*$"
    )
    if re.search(negation_pattern, prefix, re.IGNORECASE):
        return True

    return False


def _resolve_allergen_name(memory: Memory) -> str:
    """Extract a canonical allergen name from a Memory record."""
    if isinstance(memory.structured, dict):
        allergen = memory.structured.get("allergen")
        if allergen and isinstance(allergen, str):
            return allergen.strip().lower()

    # Fallback to tags if available
    for tag in memory.tags:
        cleaned_tag = tag.strip().lower()
        if cleaned_tag in ALLERGEN_SYNONYMS or any(cleaned_tag in syns for syns in ALLERGEN_SYNONYMS.values()):
            return cleaned_tag

    # Fallback: extract from memory text e.g. "Allergic to peanuts"
    text_match = re.search(r"(?:allergic to|allergy(?::|\s+to))\s+([a-zA-Z\s]+)", memory.text, re.IGNORECASE)
    if text_match:
        return text_match.group(1).strip().lower()

    return memory.text.strip().lower()


def _get_search_terms(allergen: str) -> list[str]:
    """Retrieve all search terms, synonyms, and plural/singular forms for an allergen."""
    allergen_norm = allergen.strip().lower()
    terms: set[str] = {allergen_norm}

    # Add plural / singular
    if allergen_norm.endswith("s") and len(allergen_norm) > 3:
        terms.add(allergen_norm[:-1])
    else:
        terms.add(allergen_norm + "s")

    # Look up in synonyms map
    for root_allergen, syn_list in ALLERGEN_SYNONYMS.items():
        if allergen_norm == root_allergen or allergen_norm in syn_list:
            terms.update(syn.lower() for syn in syn_list)
            terms.add(root_allergen)

    # Sort descending by length so longer phrases (e.g. "tree nuts") match before shorter ("nuts")
    return sorted(list(terms), key=lambda x: len(x), reverse=True)


def check_allergen_conflicts(answer_text: str, allergy_memories: list[Memory]) -> list[SafetyFinding]:
    """Inspect answer text against active allergy memories to detect potential conflicts."""
    findings: list[SafetyFinding] = []
    if not answer_text or not allergy_memories:
        return findings

    matched_spans: list[tuple[int, int]] = []

    for mem in allergy_memories:
        if mem.type != MemoryType.ALLERGY:
            continue

        canonical_allergen = _resolve_allergen_name(mem)
        search_terms = _get_search_terms(canonical_allergen)

        for term in search_terms:
            pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
            for m in pattern.finditer(answer_text):
                start, end = m.span()
                # Avoid overlapping spans already matched for this or longer terms
                if any(s <= start and end <= e for (s, e) in matched_spans):
                    continue

                if _is_negated(answer_text, start, end):
                    continue

                matched_spans.append((start, end))
                matched_word = m.group(0)
                findings.append(
                    SafetyFinding(
                        allergen=canonical_allergen,
                        matched_term=matched_word,
                        reason=f"Found term '{matched_word}' in recommendation conflicting with known allergy '{canonical_allergen}'."
                    )
                )

    return findings
