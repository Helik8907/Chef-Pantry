"""Multi-factor memory ranking, scoring, explanation, and reranking module.

Pure Python domain module. Zero I/O, no network, no database, no external dependencies.
All time-dependent functions accept an explicit datetime `now` for full test determinism.
"""

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Callable, Optional

from app.domain.models import (
    Memory,
    MemoryType,
    RecalledMemory,
    ScoreBreakdown,
    ensure_timezone_aware,
    utc_now,
)
from app.domain.policies import (
    DEFAULT_WEIGHTS,
    RankingWeights,
    get_policy,
)

# ============================================================================
# CONSTANTS & CONFIGURATION
# ============================================================================

# Trigger words indicating culinary cooking or meal preparation intent
COOKING_INTENT_WORDS: frozenset[str] = frozenset({
    "cook",
    "make",
    "dinner",
    "lunch",
    "breakfast",
    "tonight",
    "recipe",
    "what should i",
})

# Dampening factor applied to pantry memories for non-cooking queries
PANTRY_NON_COOKING_MULTIPLIER: float = 0.6

# Boost bump for meal outcome memories containing detailed written feedback
FEEDBACK_TEXT_BUMP: float = 0.1

# Scaling coefficient for logarithmic usage bonus: 0.2 * ln(1 + use_count)
USAGE_LOG_SCALE_FACTOR: float = 0.2

# Maximum number of human-readable justification reasons returned per memory
MAX_REASONS: int = 4


def _has_cooking_intent(query_text: Optional[str]) -> bool:
    """Check whether query contains any culinary or meal preparation intent keywords."""
    if not query_text:
        return False
    normalized = query_text.strip().lower()
    return any(intent in normalized for intent in COOKING_INTENT_WORDS)


# ============================================================================
# CANDIDATE DATACLASS
# ============================================================================

@dataclass(frozen=True)
class Candidate:
    """Raw retrieval candidate combining a Memory record with its vector similarity score.

    Attributes:
        memory: Core domain memory entity.
        similarity: Raw similarity score from vector search.
    """
    memory: Memory
    similarity: float


# ============================================================================
# PUBLIC FUNCTIONS
# ============================================================================

def score_memory(
    memory: Memory,
    similarity: float,
    now: datetime,
    query_text: Optional[str] = None,
    weights: RankingWeights = DEFAULT_WEIGHTS,
) -> ScoreBreakdown:
    """Calculate multi-factor retrieval score and breakdown for a memory candidate.

    Args:
        memory: The memory record to score.
        similarity: Incoming vector similarity score (clamped to [0.0, 1.0]).
        now: Reference timezone-aware UTC datetime.
        query_text: User conversational query text for intent detection.
        weights: Multi-factor ranking weights.

    Returns:
        ScoreBreakdown model detailing individual factors and composite final score.
    """
    ensure_timezone_aware(now)
    policy = get_policy(memory.type)

    # 1. Similarity factor clamped to [0.0, 1.0]
    sim_clamped = max(0.0, min(1.0, float(similarity)))

    # 2. Recency factor with exponential half-life decay
    if policy.recency_half_life_days is None or policy.recency_half_life_days <= 0:
        recency = 1.0
    else:
        ref_time = memory.last_used_at or memory.created_at
        elapsed_seconds = max(0.0, (now - ref_time).total_seconds())
        elapsed_days = elapsed_seconds / 86400.0
        recency = 0.5 ** (elapsed_days / policy.recency_half_life_days)
        recency = max(0.0, min(1.0, recency))

    # 3. Rating signal boost for meal outcomes
    rating_boost = 0.0
    if memory.type == MemoryType.MEAL_OUTCOME:
        raw_rating = memory.structured.get("rating")
        if isinstance(raw_rating, (int, float)):
            # Both loved (5) and disliked (1) are salient; 3 is neutral
            rating_signal = abs(float(raw_rating) - 3.0) / 2.0
            rating_boost = max(0.0, min(1.0, rating_signal))

        feedback_text = memory.structured.get("feedback")
        if isinstance(feedback_text, str) and feedback_text.strip():
            rating_boost = min(1.0, rating_boost + FEEDBACK_TEXT_BUMP)

    # 4. Type priority from policy in [0.0, 1.0]
    type_priority = max(0.0, min(1.0, policy.type_priority))

    # 5. Usage bonus scaled logarithmically
    usage_score = min(1.0, USAGE_LOG_SCALE_FACTOR * math.log1p(max(0, memory.use_count)))

    # 6. Composite weighted final score
    composite_score = (
        weights.similarity * sim_clamped
        + weights.recency * recency
        + weights.rating_signal * rating_boost
        + weights.type_priority * type_priority
        + weights.usage * usage_score
    )

    # 7. Cooking-intent adjustment for pantry items
    if memory.type == MemoryType.PANTRY and not _has_cooking_intent(query_text):
        composite_score *= PANTRY_NON_COOKING_MULTIPLIER

    final_score = round(max(0.0, min(1.0, composite_score)), 4)

    return ScoreBreakdown(
        similarity=round(sim_clamped, 4),
        recency=round(recency, 4),
        rating_boost=round(rating_boost, 4),
        type_priority=round(type_priority, 4),
        final_score=final_score,
    )


def explain(
    memory: Memory,
    breakdown: ScoreBreakdown,
    now: datetime,
) -> list[str]:
    """Generate human-readable justification reasons explaining why a memory was ranked.

    Args:
        memory: Domain memory instance.
        breakdown: Calculated score breakdown.
        now: Reference timezone-aware UTC datetime.

    Returns:
        List of up to 4 human-readable strings ordered by importance.
    """
    ensure_timezone_aware(now)
    reasons: list[str] = []

    # 1. Semantic match strength
    reasons.append(f"semantic match ({breakdown.similarity:.2f})")

    # 2. Type-specific rules and salience
    if memory.type == MemoryType.ALLERGY:
        reasons.append("type: allergy (always applied)")
    elif memory.type == MemoryType.MEAL_OUTCOME:
        raw_rating = memory.structured.get("rating")
        if isinstance(raw_rating, (int, float)):
            int_rating = int(raw_rating)
            if int_rating >= 4:
                reasons.append(f"loved dish: rated {int_rating}/5")
            elif int_rating <= 2:
                reasons.append(f"disliked dish: rated {int_rating}/5, avoid repeating")
            else:
                reasons.append(f"dish outcome: rated {int_rating}/5")
    elif memory.type == MemoryType.PANTRY:
        if memory.expires_at is not None:
            remaining_seconds = (memory.expires_at - now).total_seconds()
            remaining_days = max(0, int(remaining_seconds / 86400.0))
            if remaining_days == 0:
                reasons.append("pantry item expires today")
            else:
                reasons.append(f"pantry item expires in {remaining_days} days")
    elif memory.type == MemoryType.PREFERENCE:
        reasons.append("preference stays relevant for months")

    # 3. Recency / usage signal
    if memory.last_used_at is not None and breakdown.recency > 0.7:
        reasons.append("used recently")

    return reasons[:MAX_REASONS]


def rank(
    candidates: list[Candidate],
    now: datetime,
    query_text: Optional[str] = None,
    weights: RankingWeights = DEFAULT_WEIGHTS,
    top_k: int = 5,
    min_score: float = 0.0,
    max_per_type: Optional[int] = None,
) -> list[RecalledMemory]:
    """Filter, score, tie-break, and rank retrieval candidates into RecalledMemory items.

    Never mutates input memories. Never injects or special-cases allergies (always-applied
    guardrails remain strictly in the recall service).

    Args:
        candidates: Candidate memory items paired with raw vector similarity scores.
        now: Reference timezone-aware UTC datetime.
        query_text: User conversational query for intent detection.
        weights: Multi-factor ranking weights.
        top_k: Maximum number of ranked results to return.
        min_score: Minimum composite score cutoff.
        max_per_type: Maximum items of any single memory type to prevent flooding.

    Returns:
        List of RecalledMemory instances sorted by rank.
    """
    ensure_timezone_aware(now)

    # 1. Score active and non-expired candidates
    scored_items: list[tuple[Candidate, ScoreBreakdown]] = []
    for cand in candidates:
        if not cand.memory.is_active(now):
            continue

        breakdown = score_memory(
            memory=cand.memory,
            similarity=cand.similarity,
            now=now,
            query_text=query_text,
            weights=weights,
        )

        if breakdown.final_score >= min_score:
            scored_items.append((cand, breakdown))

    # 2. Sort with deterministic tie-breaking:
    #    Highest final_score, then highest similarity, then newest created_at, then ID
    scored_items.sort(
        key=lambda pair: (
            -pair[1].final_score,
            -pair[1].similarity,
            -pair[0].memory.created_at.timestamp(),
            str(pair[0].memory.id),
        )
    )

    # 3. Apply diversity per-type cap and top_k limit
    type_counts: dict[MemoryType, int] = {}
    recalled_list: list[RecalledMemory] = []

    for cand, breakdown in scored_items:
        mem_type = cand.memory.type
        if max_per_type is not None:
            current_count = type_counts.get(mem_type, 0)
            if current_count >= max_per_type:
                continue
            type_counts[mem_type] = current_count + 1

        recalled = RecalledMemory.model_construct(
            memory=cand.memory,
            score=breakdown,
            reasons=explain(cand.memory, breakdown, now),
            matched_filters={},
        )
        recalled_list.append(recalled)

        if len(recalled_list) >= top_k:
            break

    return recalled_list


def make_reranker(
    weights: RankingWeights = DEFAULT_WEIGHTS,
    now_fn: Optional[Callable[[], datetime]] = None,
    top_k: int = 5,
    min_score: float = 0.0,
    max_per_type: Optional[int] = None,
) -> Callable[..., list[RecalledMemory]]:
    """Create a reranker callable compatible with MemoryRecall.

    Exact signature of the returned callable:
        `rerank(items: list[RecalledMemory], query_text: Optional[str] = None) -> list[RecalledMemory]`

    Integration note regarding MemoryRecall:
        In `app/services/memory_recall.py`, `MemoryRecall.recall` calls `self.rerank(recalled_candidates)`
        with only 1 positional argument (items) and does not pass `query_text`.
        This returned callable supports being invoked with 1 argument (`rerank(items)`)
        or with 2 arguments (`rerank(items, query_text)`). When invoked with 1 argument,
        `query_text` defaults to None.
    """
    def rerank_callable(
        items: list[RecalledMemory],
        query_text: Optional[str] = None,
    ) -> list[RecalledMemory]:
        now = now_fn() if now_fn is not None else utc_now()
        candidates = [
            Candidate(memory=item.memory, similarity=item.score.similarity)
            for item in items
        ]
        return rank(
            candidates=candidates,
            now=now,
            query_text=query_text,
            weights=weights,
            top_k=top_k,
            min_score=min_score,
            max_per_type=max_per_type,
        )

    return rerank_callable

