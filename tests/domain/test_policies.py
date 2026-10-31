"""Tests for domain model validation rules in app.domain.models."""

from datetime import datetime, timedelta
import pytest
from pydantic import ValidationError

from app.domain.models import (
    Memory,
    MemoryType,
    MemoryStatus,
    User,
    utc_now,
)


def test_allergy_forced_protected_and_no_expiry():
    """Allergy type memories must force protected=True and expires_at=None."""
    future_expiry = utc_now() + timedelta(days=30)
    memory = Memory(
        user_id="user_123",
        type=MemoryType.ALLERGY,
        text="Allergic to peanuts",
        protected=False,
        expires_at=future_expiry,
    )
    assert memory.protected is True
    assert memory.expires_at is None


def test_tag_normalization():
    """Tags must be stripped, lowercased, and de-duplicated."""
    raw_tags = ["  Vegan ", "GLUTEN-FREE", "vegan", "  ", "gluten-free  ", "Nut-Free"]
    memory = Memory(
        user_id="user_123",
        type=MemoryType.PREFERENCE,
        text="Loves plant-based meals",
        tags=raw_tags,
    )
    assert memory.tags == ["vegan", "gluten-free", "nut-free"]


def test_empty_text_rejected():
    """Empty or whitespace-only text must be rejected."""
    with pytest.raises(ValidationError):
        Memory(
            user_id="user_123",
            type=MemoryType.PREFERENCE,
            text="",
        )

    with pytest.raises(ValidationError):
        Memory(
            user_id="user_123",
            type=MemoryType.PREFERENCE,
            text="   \n\t  ",
        )


def test_is_expired_behavior():
    """is_expired and is_active should accurately reflect expiry and status."""
    now = utc_now()

    # Expired memory
    past_memory = Memory(
        user_id="user_123",
        type=MemoryType.TEMPORARY_CONTEXT,
        text="Hosting dinner tonight",
        expires_at=now - timedelta(hours=2),
    )
    assert past_memory.is_expired(now) is True
    assert past_memory.is_active(now) is False

    # Active future memory
    future_memory = Memory(
        user_id="user_123",
        type=MemoryType.TEMPORARY_CONTEXT,
        text="Cooking for 4 guests tomorrow",
        expires_at=now + timedelta(hours=24),
    )
    assert future_memory.is_expired(now) is False
    assert future_memory.is_active(now) is True

    # Memory with no expiry
    no_expiry_memory = Memory(
        user_id="user_123",
        type=MemoryType.PREFERENCE,
        text="Prefers spicy food",
        expires_at=None,
    )
    assert no_expiry_memory.is_expired(now) is False
    assert no_expiry_memory.is_active(now) is True

    # Superseded or deleted memory is not active even if not expired
    superseded_memory = Memory(
        user_id="user_123",
        type=MemoryType.PREFERENCE,
        text="Old spicy preference",
        status=MemoryStatus.SUPERSEDED,
        superseded_by="mem_new_999",
    )
    assert superseded_memory.is_active(now) is False


def test_naive_datetime_rejected():
    """Naive datetimes must be rejected by validators."""
    naive_dt = datetime(2026, 12, 1, 10, 0, 0)

    with pytest.raises(ValidationError):
        Memory(
            user_id="user_123",
            type=MemoryType.TEMPORARY_CONTEXT,
            text="Dinner event",
            expires_at=naive_dt,
        )

    with pytest.raises(ValidationError):
        User(
            user_id="chef_bob",
            display_name="Chef Bob",
            created_at=naive_dt,
        )



# ============================================================================
# POLICY & RANKING WEIGHT TESTS
# ============================================================================

from app.domain.policies import (
    DEFAULT_WEIGHTS,
    MAX_TTL_PANTRY,
    MAX_TTL_TEMPORARY_CONTEXT,
    POLICIES,
    RankingWeights,
    TypePolicy,
    can_auto_supersede,
    compute_expires_at,
    get_policy,
    is_protected,
    requires_confirmation,
)


def test_ranking_weights_validation():
    """RankingWeights must sum to 1.0 or raise ValueError."""
    # Valid default weights
    assert DEFAULT_WEIGHTS.similarity == 0.55
    total = (
        DEFAULT_WEIGHTS.similarity
        + DEFAULT_WEIGHTS.recency
        + DEFAULT_WEIGHTS.rating_signal
        + DEFAULT_WEIGHTS.type_priority
        + DEFAULT_WEIGHTS.usage
    )
    assert abs(total - 1.0) < 1e-6

    # Custom valid weights
    custom = RankingWeights(
        similarity=0.4,
        recency=0.2,
        rating_signal=0.2,
        type_priority=0.1,
        usage=0.1,
    )
    assert custom.similarity == 0.4

    # Weights summing to less than 1.0
    with pytest.raises(ValueError, match="must sum to 1.0"):
        RankingWeights(
            similarity=0.3,
            recency=0.2,
            rating_signal=0.2,
            type_priority=0.1,
            usage=0.1,
        )

    # Weights summing to greater than 1.0
    with pytest.raises(ValueError, match="must sum to 1.0"):
        RankingWeights(
            similarity=0.6,
            recency=0.2,
            rating_signal=0.2,
            type_priority=0.1,
            usage=0.1,
        )


def test_allergy_policy_attributes():
    """Allergy policy must be protected, have no ttl, highest priority, and always apply."""
    policy = get_policy(MemoryType.ALLERGY)
    assert policy.ttl is None
    assert policy.protected is True
    assert policy.auto_supersede_allowed is False
    assert policy.requires_confirmation_to_change is True
    assert policy.type_priority == 1.0
    assert policy.recency_half_life_days is None
    assert policy.always_apply is True


def test_pantry_and_temporary_policies():
    """Pantry and temporary context policies must reflect expected TTLs and half-lives."""
    pantry_pol = get_policy(MemoryType.PANTRY, demo_mode=False)
    assert pantry_pol.ttl == timedelta(days=3)
    assert pantry_pol.protected is False
    assert pantry_pol.auto_supersede_allowed is True
    assert pantry_pol.type_priority == 0.2
    assert pantry_pol.recency_half_life_days == 3.0

    temp_pol = get_policy(MemoryType.TEMPORARY_CONTEXT, demo_mode=False)
    assert temp_pol.ttl == timedelta(hours=24)
    assert temp_pol.protected is False
    assert temp_pol.auto_supersede_allowed is True
    assert temp_pol.type_priority == 0.5
    assert temp_pol.recency_half_life_days == 1.0

    pref_pol = get_policy(MemoryType.PREFERENCE)
    assert pref_pol.ttl is None
    assert pref_pol.type_priority == 0.8
    assert pref_pol.recency_half_life_days == 180.0
    assert pref_pol.always_apply is True

    meal_pol = get_policy(MemoryType.MEAL_OUTCOME)
    assert meal_pol.ttl is None
    assert meal_pol.type_priority == 0.6
    assert meal_pol.recency_half_life_days == 60.0


def test_demo_mode_override():
    """Demo mode must override TTL for pantry and temporary context to demo TTL."""
    pantry_demo = get_policy(MemoryType.PANTRY, demo_mode=True)
    assert pantry_demo.ttl == timedelta(seconds=60)

    temp_demo = get_policy(MemoryType.TEMPORARY_CONTEXT, demo_mode=True)
    assert temp_demo.ttl == timedelta(seconds=60)

    # Permanent types remain untouched in demo mode
    allergy_demo = get_policy(MemoryType.ALLERGY, demo_mode=True)
    assert allergy_demo.ttl is None


def test_compute_expires_at_no_ttl_for_permanent_types():
    """Permanent memory types (allergy, preference, meal_outcome) must return None for expiry."""
    now = utc_now()
    assert compute_expires_at(MemoryType.ALLERGY, now) is None
    assert compute_expires_at(MemoryType.PREFERENCE, now) is None
    assert compute_expires_at(MemoryType.MEAL_OUTCOME, now) is None


def test_compute_expires_at_caps_and_defaults():
    """compute_expires_at should use defaults and enforce maximum allowable caps."""
    now = utc_now()

    # Pantry default 3 days
    pantry_default_exp = compute_expires_at(MemoryType.PANTRY, now, demo_mode=False)
    assert pantry_default_exp == now + timedelta(days=3)

    # Pantry suggested 48 hours (within cap)
    pantry_suggested = compute_expires_at(MemoryType.PANTRY, now, suggested_ttl_hours=48, demo_mode=False)
    assert pantry_suggested == now + timedelta(hours=48)

    # Pantry suggested exceeding cap (e.g. 30 days -> capped at 14 days)
    pantry_capped = compute_expires_at(MemoryType.PANTRY, now, suggested_ttl_hours=720, demo_mode=False)
    assert pantry_capped == now + MAX_TTL_PANTRY

    # Temporary context suggested exceeding cap (e.g. 20 days -> capped at 7 days)
    temp_capped = compute_expires_at(MemoryType.TEMPORARY_CONTEXT, now, suggested_ttl_hours=480, demo_mode=False)
    assert temp_capped == now + MAX_TTL_TEMPORARY_CONTEXT


def test_compute_expires_at_demo_override_wins():
    """Demo mode must take precedence over suggested TTL and defaults."""
    now = utc_now()
    demo_exp = compute_expires_at(
        MemoryType.PANTRY,
        now,
        suggested_ttl_hours=200,
        demo_mode=True,
    )
    assert demo_exp == now + timedelta(seconds=60)


def test_policy_helpers():
    """Helper functions must return the expected booleans according to policies."""
    assert is_protected(MemoryType.ALLERGY) is True
    assert is_protected(MemoryType.PREFERENCE) is False
    assert is_protected(MemoryType.PANTRY) is False

    assert can_auto_supersede(MemoryType.ALLERGY) is False
    assert can_auto_supersede(MemoryType.PREFERENCE) is True
    assert can_auto_supersede(MemoryType.PANTRY) is True

    assert requires_confirmation(MemoryType.ALLERGY) is True
    assert requires_confirmation(MemoryType.PREFERENCE) is False
    assert requires_confirmation(MemoryType.PANTRY) is False
