"""Unit tests for heuristic allergen safety checking and boundary detection."""

import pytest
from app.domain.models import Memory, MemoryStatus, MemoryType
from app.domain.safety import ALLERGEN_SYNONYMS, SafetyFinding, check_allergen_conflicts


def create_allergy_memory(allergen: str, mem_id: str = "0123456789abcdef01234567") -> Memory:
    """Helper to construct a test allergy memory."""
    return Memory.model_construct(
        id=mem_id,
        user_id="user_test",
        type=MemoryType.ALLERGY,
        text=f"Allergic to {allergen}",
        structured={"allergen": allergen, "severity": "severe"},
        tags=[allergen],
        status=MemoryStatus.ACTIVE,
        protected=True,
        expires_at=None,
    )


def test_safety_clean_text() -> None:
    """Verify that safe text without any conflicting allergens produces zero findings."""
    mem = create_allergy_memory("peanut")
    findings = check_allergen_conflicts("Enjoy a fresh bowl of steamed broccoli and quinoa.", [mem])
    assert findings == []


def test_safety_direct_allergen_match() -> None:
    """Verify direct match of allergen word flags conflict."""
    mem = create_allergy_memory("peanut")
    findings = check_allergen_conflicts("Drizzle with warm peanut sauce.", [mem])
    assert len(findings) == 1
    assert findings[0].allergen == "peanut"
    assert findings[0].matched_term.lower() == "peanut"


def test_safety_plural_matching() -> None:
    """Verify that plural form of allergen is correctly detected."""
    mem = create_allergy_memory("peanut")
    findings = check_allergen_conflicts("Garnish with roasted peanuts on top.", [mem])
    assert len(findings) == 1
    assert findings[0].allergen == "peanut"
    assert findings[0].matched_term.lower() == "peanuts"


def test_safety_synonym_matching() -> None:
    """Verify that synonyms from ALLERGEN_SYNONYMS trigger detection."""
    milk_mem = create_allergy_memory("milk")

    # 'ghee' is a synonym for milk/dairy
    findings_ghee = check_allergen_conflicts("Sauté vegetables in two tablespoons of ghee.", [milk_mem])
    assert len(findings_ghee) == 1
    assert findings_ghee[0].allergen == "milk"
    assert findings_ghee[0].matched_term.lower() == "ghee"

    # 'butter' is a synonym for milk/dairy
    findings_butter = check_allergen_conflicts("Melt butter in a skillet.", [milk_mem])
    assert len(findings_butter) == 1
    assert findings_butter[0].allergen == "milk"
    assert findings_butter[0].matched_term.lower() == "butter"

    # 'paneer' is a synonym for milk/dairy
    findings_paneer = check_allergen_conflicts("Add cubes of fried paneer.", [milk_mem])
    assert len(findings_paneer) == 1
    assert findings_paneer[0].allergen == "milk"
    assert findings_paneer[0].matched_term.lower() == "paneer"

    # 'mayo' is a synonym for egg
    egg_mem = create_allergy_memory("egg")
    findings_mayo = check_allergen_conflicts("Spread a layer of mayo over the sandwich.", [egg_mem])
    assert len(findings_mayo) == 1
    assert findings_mayo[0].allergen == "egg"
    assert findings_mayo[0].matched_term.lower() == "mayo"


def test_safety_boundary_matching() -> None:
    """Verify word boundary regex prevents spurious partial substring matches."""
    fish_mem = create_allergy_memory("fish")

    # 'selfish' contains 'fish' as substring but should not match
    findings = check_allergen_conflicts("Don't be selfish, share your food.", [fish_mem])
    assert findings == []

    # Actual 'fish' should match
    findings_fish = check_allergen_conflicts("Grilled white fish with lemon.", [fish_mem])
    assert len(findings_fish) == 1


def test_safety_negation_suffix() -> None:
    """Verify '-free' and ' free' suffix negations are not flagged."""
    mem = create_allergy_memory("peanut")

    # 'peanut-free'
    findings_hyphen = check_allergen_conflicts("Serve with crispy peanut-free cookies.", [mem])
    assert findings_hyphen == []

    # 'peanut free'
    findings_space = check_allergen_conflicts("This bakery item is 100% peanut free.", [mem])
    assert findings_space == []

    # But regular 'peanut' is flagged
    findings_real = check_allergen_conflicts("Peanut brittle for dessert.", [mem])
    assert len(findings_real) == 1


def test_safety_negation_prefix() -> None:
    """Verify prefix negations like 'without', 'no', 'free from' are not flagged."""
    mem = create_allergy_memory("peanut")

    findings_without = check_allergen_conflicts("Prepare pad thai without peanuts.", [mem])
    assert findings_without == []

    findings_no = check_allergen_conflicts("Made with no peanuts or nuts.", [mem])
    assert findings_no == []

    findings_free_from = check_allergen_conflicts("Guaranteed free from peanuts.", [mem])
    assert findings_free_from == []


def test_safety_non_allergy_memories_ignored() -> None:
    """Verify that memories with type other than ALLERGY are ignored by safety checker."""
    pref_mem = Memory.model_construct(
        id="0123456789abcdef01234567",
        user_id="user_test",
        type=MemoryType.PREFERENCE,
        text="Dislikes peanuts",
        structured={"kind": "dislike", "item": "peanuts"},
        tags=["peanut"],
        status=MemoryStatus.ACTIVE,
        protected=False,
        expires_at=None,
    )
    findings = check_allergen_conflicts("Drizzle with peanut oil.", [pref_mem])
    assert findings == []
