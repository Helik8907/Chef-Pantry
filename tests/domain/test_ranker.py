"""Unit tests for multi-factor memory ranker, scoring, and explanation module."""

from datetime import datetime, timedelta, timezone
import pytest

from app.domain.models import (
    Memory,
    MemoryStatus,
    MemoryType,
    RecalledMemory,
    ScoreBreakdown,
)
from app.domain.policies import DEFAULT_WEIGHTS, RankingWeights
from app.domain.ranker import (
    Candidate,
    explain,
    make_reranker,
    rank,
    score_memory,
)


@pytest.fixture
def fixed_now() -> datetime:
    """Deterministic reference datetime for time-dependent ranking tests."""
    return datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


def test_recency_decay_at_one_half_life(fixed_now: datetime):
    """Recency score should decay to approximately 0.5 at exactly one half-life."""
    # Temporary context has half-life of 1.0 day (24 hours)
    created_at = fixed_now - timedelta(days=1)
    memory = Memory(
        id="010101010101010101010101",
        user_id="user_123",
        type=MemoryType.TEMPORARY_CONTEXT,
        text="Hosting dinner guests",
        created_at=created_at,
    )

    breakdown = score_memory(
        memory=memory,
        similarity=1.0,
        now=fixed_now,
    )
    assert pytest.approx(breakdown.recency, abs=0.01) == 0.5


def test_meal_outcome_salience_rating_boost(fixed_now: datetime):
    """1-star and 5-star meal outcomes both outrank 3-star neutral outcomes at equal similarity."""
    mem_loved = Memory(
        id="111111111111111111111111",
        user_id="user_123",
        type=MemoryType.MEAL_OUTCOME,
        text="Loved the mushroom risotto",
        structured={"dish": "mushroom risotto", "rating": 5},
        created_at=fixed_now,
    )
    mem_disliked = Memory(
        id="222222222222222222222222",
        user_id="user_123",
        type=MemoryType.MEAL_OUTCOME,
        text="Disliked the bitter kale salad",
        structured={"dish": "kale salad", "rating": 1},
        created_at=fixed_now,
    )
    mem_neutral = Memory(
        id="333333333333333333333333",
        user_id="user_123",
        type=MemoryType.MEAL_OUTCOME,
        text="Average plain pasta",
        structured={"dish": "plain pasta", "rating": 3},
        created_at=fixed_now,
    )

    score_loved = score_memory(mem_loved, similarity=0.8, now=fixed_now)
    score_disliked = score_memory(mem_disliked, similarity=0.8, now=fixed_now)
    score_neutral = score_memory(mem_neutral, similarity=0.8, now=fixed_now)

    assert score_loved.rating_boost == 1.0
    assert score_disliked.rating_boost == 1.0
    assert score_neutral.rating_boost == 0.0

    assert score_loved.final_score == score_disliked.final_score
    assert score_loved.final_score > score_neutral.final_score


def test_meal_outcome_feedback_text_bump(fixed_now: datetime):
    """Meal outcome with structured feedback text gets an extra boost bump."""
    mem_with_feedback = Memory(
        id="444444444444444444444444",
        user_id="user_123",
        type=MemoryType.MEAL_OUTCOME,
        text="Good soup",
        structured={"dish": "soup", "rating": 4, "feedback": "Needs a touch more salt next time"},
        created_at=fixed_now,
    )
    mem_no_feedback = Memory(
        id="555555555555555555555555",
        user_id="user_123",
        type=MemoryType.MEAL_OUTCOME,
        text="Good soup",
        structured={"dish": "soup", "rating": 4},
        created_at=fixed_now,
    )

    score_fb = score_memory(mem_with_feedback, similarity=0.8, now=fixed_now)
    score_no_fb = score_memory(mem_no_feedback, similarity=0.8, now=fixed_now)

    assert score_fb.rating_boost > score_no_fb.rating_boost
    assert score_fb.final_score > score_no_fb.final_score


def test_inactive_and_expired_memories_excluded(fixed_now: datetime):
    """Expired, superseded, and soft-deleted memories must be excluded from rank results."""
    active_valid = Memory(
        id="aaaaaaaaaaaaaaaaaaaaaaaa",
        user_id="user_1",
        type=MemoryType.PREFERENCE,
        text="Loves garlic",
        created_at=fixed_now,
    )
    expired_mem = Memory(
        id="bbbbbbbbbbbbbbbbbbbbbbbb",
        user_id="user_1",
        type=MemoryType.TEMPORARY_CONTEXT,
        text="Old party",
        expires_at=fixed_now - timedelta(hours=1),
        created_at=fixed_now - timedelta(days=2),
    )
    superseded_mem = Memory(
        id="cccccccccccccccccccccccc",
        user_id="user_1",
        type=MemoryType.PREFERENCE,
        text="Hates onions",
        status=MemoryStatus.SUPERSEDED,
        superseded_by="aaaaaaaaaaaaaaaaaaaaaaaa",
        created_at=fixed_now - timedelta(days=5),
    )
    deleted_mem = Memory(
        id="dddddddddddddddddddddddd",
        user_id="user_1",
        type=MemoryType.PANTRY,
        text="Expired milk",
        status=MemoryStatus.DELETED,
        deleted_at=fixed_now - timedelta(hours=2),
        created_at=fixed_now - timedelta(days=3),
    )

    candidates = [
        Candidate(memory=active_valid, similarity=0.9),
        Candidate(memory=expired_mem, similarity=0.95),
        Candidate(memory=superseded_mem, similarity=0.99),
        Candidate(memory=deleted_mem, similarity=0.98),
    ]

    results = rank(candidates=candidates, now=fixed_now)
    assert len(results) == 1
    assert results[0].memory.id == active_valid.id


def test_deterministic_tie_breaking(fixed_now: datetime):
    """Ties in final_score must break by similarity, then newer created_at, then ID."""
    # Build 3 preference items with identical scores except subtle tie factors
    older_ts = fixed_now - timedelta(days=2)
    newer_ts = fixed_now - timedelta(days=1)

    mem_higher_sim = Memory(
        id="111111111111111111111111",
        user_id="user_1",
        type=MemoryType.PREFERENCE,
        text="Pref A",
        created_at=older_ts,
    )
    mem_newer_ts = Memory(
        id="222222222222222222222222",
        user_id="user_1",
        type=MemoryType.PREFERENCE,
        text="Pref B",
        created_at=newer_ts,
    )
    mem_older_ts = Memory(
        id="333333333333333333333333",
        user_id="user_1",
        type=MemoryType.PREFERENCE,
        text="Pref C",
        created_at=older_ts,
    )

    # Give mem_higher_sim 0.85 similarity, and the other two 0.80 similarity
    candidates = [
        Candidate(memory=mem_older_ts, similarity=0.80),
        Candidate(memory=mem_higher_sim, similarity=0.85),
        Candidate(memory=mem_newer_ts, similarity=0.80),
    ]

    results = rank(candidates=candidates, now=fixed_now, top_k=3)
    # 1st: mem_higher_sim (highest similarity)
    assert results[0].memory.id == mem_higher_sim.id
    # 2nd: mem_newer_ts (newer created_at breaks tie between 0.80 similarity items)
    assert results[1].memory.id == mem_newer_ts.id
    # 3rd: mem_older_ts
    assert results[2].memory.id == mem_older_ts.id


def test_max_per_type_and_min_score(fixed_now: datetime):
    """max_per_type prevents single-type flooding and min_score filters out weak matches."""
    mem_p1 = Memory(id="010101010101010101010101", user_id="u", type=MemoryType.PREFERENCE, text="Pref 1", created_at=fixed_now)
    mem_p2 = Memory(id="020202020202020202020202", user_id="u", type=MemoryType.PREFERENCE, text="Pref 2", created_at=fixed_now)
    mem_p3 = Memory(id="030303030303030303030303", user_id="u", type=MemoryType.PREFERENCE, text="Pref 3", created_at=fixed_now)
    mem_pan1 = Memory(id="040404040404040404040404", user_id="u", type=MemoryType.PANTRY, text="Olive oil", created_at=fixed_now)
    mem_weak = Memory(id="050505050505050505050505", user_id="u", type=MemoryType.PREFERENCE, text="Weak match", created_at=fixed_now)

    candidates = [
        Candidate(memory=mem_p1, similarity=0.9),
        Candidate(memory=mem_p2, similarity=0.85),
        Candidate(memory=mem_p3, similarity=0.8),
        Candidate(memory=mem_pan1, similarity=0.75),
        Candidate(memory=mem_weak, similarity=0.01),
    ]

    # With max_per_type=2, only 2 preferences should be included even if p3 is better than pan1
    results = rank(
        candidates=candidates,
        now=fixed_now,
        query_text="cook dinner",
        top_k=5,
        min_score=0.3,
        max_per_type=2,
    )

    types = [rm.memory.type for rm in results]
    assert types.count(MemoryType.PREFERENCE) == 2
    assert types.count(MemoryType.PANTRY) == 1
    # mem_weak should be completely filtered out by min_score=0.3
    assert not any(rm.memory.id == mem_weak.id for rm in results)


def test_pantry_cooking_intent_downweighting(fixed_now: datetime):
    """Pantry score is preserved for cooking intent and dampened for non-cooking queries."""
    pantry_mem = Memory(
        id="121212121212121212121212",
        user_id="user_123",
        type=MemoryType.PANTRY,
        text="2 cans diced tomatoes",
        created_at=fixed_now,
    )

    # Cooking query
    score_cooking = score_memory(
        memory=pantry_mem,
        similarity=0.8,
        now=fixed_now,
        query_text="What should I cook for dinner tonight?",
    )

    # Non-cooking query
    score_non_cooking = score_memory(
        memory=pantry_mem,
        similarity=0.8,
        now=fixed_now,
        query_text="Tell me a joke about dogs",
    )

    # Without query text (defaults to non-cooking)
    score_no_query = score_memory(
        memory=pantry_mem,
        similarity=0.8,
        now=fixed_now,
        query_text=None,
    )

    assert score_cooking.final_score > score_non_cooking.final_score
    assert score_non_cooking.final_score == pytest.approx(score_cooking.final_score * 0.6, abs=0.01)
    assert score_no_query.final_score == score_non_cooking.final_score


def test_explain_reasons_cap_and_signals(fixed_now: datetime):
    """explain() returns at most 4 reasons containing relevant signals."""
    mem_outcome = Memory(
        id="131313131313131313131313",
        user_id="user_123",
        type=MemoryType.MEAL_OUTCOME,
        text="Amazing chicken tikka",
        structured={"dish": "chicken tikka", "rating": 5},
        created_at=fixed_now - timedelta(days=2),
        last_used_at=fixed_now - timedelta(hours=2),
        use_count=5,
    )

    breakdown = score_memory(mem_outcome, similarity=0.92, now=fixed_now)
    reasons = explain(mem_outcome, breakdown, fixed_now)

    assert len(reasons) <= 4
    assert any("semantic match (0.92)" in r for r in reasons)
    assert any("loved dish: rated 5/5" in r for r in reasons)
    assert any("used recently" in r for r in reasons)

    # Test pantry expiry reason
    pantry_mem = Memory(
        id="141414141414141414141414",
        user_id="user_123",
        type=MemoryType.PANTRY,
        text="Milk carton",
        expires_at=fixed_now + timedelta(days=2),
        created_at=fixed_now,
    )
    pantry_score = score_memory(pantry_mem, similarity=0.75, now=fixed_now)
    pantry_reasons = explain(pantry_mem, pantry_score, fixed_now)
    assert any("pantry item expires in 2 days" in r for r in pantry_reasons)


def test_weights_tuning_changes_ordering(fixed_now: datetime):
    """Changing ranking weights predictably alters candidate ordering."""
    older_relevant = Memory(
        id="212121212121212121212121",
        user_id="user_123",
        type=MemoryType.PREFERENCE,
        text="Loves spicy Thai curries",
        created_at=fixed_now - timedelta(days=150),
    )
    fresh_less_relevant = Memory(
        id="222222222222222222222222",
        user_id="user_123",
        type=MemoryType.PREFERENCE,
        text="Prefers mild food",
        created_at=fixed_now - timedelta(hours=1),
    )

    candidates = [
        Candidate(memory=older_relevant, similarity=0.95),
        Candidate(memory=fresh_less_relevant, similarity=0.50),
    ]

    # Similarity dominant: older_relevant wins
    sim_weights = RankingWeights(
        similarity=0.80,
        recency=0.05,
        rating_signal=0.05,
        type_priority=0.05,
        usage=0.05,
    )
    ranked_sim = rank(candidates, now=fixed_now, weights=sim_weights)
    assert ranked_sim[0].memory.id == older_relevant.id

    # Recency dominant: fresh_less_relevant wins
    recency_weights = RankingWeights(
        similarity=0.10,
        recency=0.75,
        rating_signal=0.05,
        type_priority=0.05,
        usage=0.05,
    )
    ranked_recency = rank(candidates, now=fixed_now, weights=recency_weights)
    assert ranked_recency[0].memory.id == fresh_less_relevant.id


def test_make_reranker_callable(fixed_now: datetime):
    """make_reranker returns a callable compatible with MemoryRecall single and two-arg calls."""
    reranker = make_reranker(now_fn=lambda: fixed_now, top_k=2)

    mem_a = Memory(id="313131313131313131313131", user_id="u", type=MemoryType.PREFERENCE, text="A", created_at=fixed_now)
    mem_b = Memory(id="323232323232323232323232", user_id="u", type=MemoryType.PREFERENCE, text="B", created_at=fixed_now)

    recalled_a = RecalledMemory.model_construct(
        memory=mem_a,
        score=ScoreBreakdown(similarity=0.6, final_score=0.6),
        reasons=[],
    )
    recalled_b = RecalledMemory.model_construct(
        memory=mem_b,
        score=ScoreBreakdown(similarity=0.9, final_score=0.9),
        reasons=[],
    )

    # 1. Single-argument call (as called by MemoryRecall in memory_recall.py line 169)
    res_single = reranker([recalled_a, recalled_b])
    assert len(res_single) == 2
    assert res_single[0].memory.id == mem_b.id

    # 2. Two-argument call with query_text
    res_double = reranker([recalled_a, recalled_b], query_text="cook dinner")
    assert len(res_double) == 2
    assert res_double[0].memory.id == mem_b.id

