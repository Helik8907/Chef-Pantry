"""Single source of truth for per-memory-type policies, ranking weights, and lifecycle rules.

Pure Python domain module. Zero I/O, no network, no database, no external dependencies.
All time-dependent functions accept an explicit or reference datetime.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import math
import os
from typing import Optional

from app.domain.models import MemoryType, ensure_timezone_aware

# ============================================================================
# CONSTANTS & CONFIGURATION
# ============================================================================

# Maximum allowable TTL caps for expiring memory types
MAX_TTL_PANTRY: timedelta = timedelta(days=14)
MAX_TTL_TEMPORARY_CONTEXT: timedelta = timedelta(days=7)

# Environment configuration defaults for interactive demos
ENV_DEMO_MODE_VAR: str = "DEMO_MODE"
ENV_DEMO_TTL_SECONDS_VAR: str = "DEMO_TTL_SECONDS"
DEFAULT_DEMO_TTL_SECONDS: int = 60


def _get_env_demo_mode() -> bool:
    """Read demo mode flag from environment variable."""
    return os.getenv(ENV_DEMO_MODE_VAR, "false").strip().lower() in ("true", "1", "yes")


def _get_env_demo_ttl_seconds() -> int:
    """Read demo TTL in seconds from environment variable."""
    raw = os.getenv(ENV_DEMO_TTL_SECONDS_VAR, str(DEFAULT_DEMO_TTL_SECONDS))
    try:
        val = int(raw.strip())
        return val if val > 0 else DEFAULT_DEMO_TTL_SECONDS
    except ValueError:
        return DEFAULT_DEMO_TTL_SECONDS


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass(frozen=True)
class TypePolicy:
    """Policy definition and governance rules for a memory type.

    Attributes:
        ttl: Default time-to-live timedelta (None for permanent types).
        protected: Whether memories of this type are protected from eviction.
        auto_supersede_allowed: Whether this memory can be automatically superseded.
        requires_confirmation_to_change: Whether human/user confirmation is required to alter.
        type_priority: Priority score in range [0.0, 1.0].
        recency_half_life_days: Exponential decay half-life in days (None for no decay).
        always_apply: Whether memories of this type are injected regardless of semantic match.
    """
    ttl: Optional[timedelta]
    protected: bool
    auto_supersede_allowed: bool
    requires_confirmation_to_change: bool
    type_priority: float
    recency_half_life_days: Optional[float]
    always_apply: bool


@dataclass(frozen=True)
class RankingWeights:
    """Weights configuration for multi-factor memory ranking.

    All components must sum up to exactly 1.0 (+/- 1e-6 tolerance).
    """
    similarity: float
    recency: float
    rating_signal: float
    type_priority: float
    usage: float

    def __post_init__(self) -> None:
        """Validate that all ranking weights sum to 1.0."""
        total = self.similarity + self.recency + self.rating_signal + self.type_priority + self.usage
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"Ranking weights must sum to 1.0, got {total:.6f} "
                f"(similarity={self.similarity}, recency={self.recency}, "
                f"rating_signal={self.rating_signal}, type_priority={self.type_priority}, "
                f"usage={self.usage})"
            )


# Default ranking weights (similarity dominant)
DEFAULT_WEIGHTS = RankingWeights(
    similarity=0.55,
    recency=0.15,
    rating_signal=0.15,
    type_priority=0.10,
    usage=0.05,
)


# ============================================================================
# POLICIES DICTIONARY
# ============================================================================

POLICIES: dict[MemoryType, TypePolicy] = {
    MemoryType.ALLERGY: TypePolicy(
        ttl=None,
        protected=True,
        auto_supersede_allowed=False,
        requires_confirmation_to_change=True,
        type_priority=1.0,
        recency_half_life_days=None,
        always_apply=True,
    ),
    MemoryType.PREFERENCE: TypePolicy(
        ttl=None,
        protected=False,
        auto_supersede_allowed=True,
        requires_confirmation_to_change=False,
        type_priority=0.8,
        recency_half_life_days=180.0,
        always_apply=True,
    ),
    MemoryType.MEAL_OUTCOME: TypePolicy(
        ttl=None,
        protected=False,
        auto_supersede_allowed=True,
        requires_confirmation_to_change=False,
        type_priority=0.6,
        recency_half_life_days=60.0,
        always_apply=False,
    ),
    MemoryType.PANTRY: TypePolicy(
        ttl=timedelta(days=3),
        protected=False,
        auto_supersede_allowed=True,
        requires_confirmation_to_change=False,
        type_priority=0.2,
        recency_half_life_days=3.0,
        always_apply=False,
    ),
    MemoryType.TEMPORARY_CONTEXT: TypePolicy(
        ttl=timedelta(hours=24),
        protected=False,
        auto_supersede_allowed=True,
        requires_confirmation_to_change=False,
        type_priority=0.5,
        recency_half_life_days=1.0,
        always_apply=False,
    ),
}


# ============================================================================
# PUBLIC FUNCTIONS
# ============================================================================

def get_policy(
    memory_type: MemoryType,
    demo_mode: Optional[bool] = None,
) -> TypePolicy:
    """Retrieve the governance policy for a given memory type with demo override support.

    Args:
        memory_type: Categorical memory type.
        demo_mode: Explicit demo flag override. If None, reads from DEMO_MODE env var.
    """
    if memory_type not in POLICIES:
        raise ValueError(f"Unknown memory type: {memory_type}")

    policy = POLICIES[memory_type]
    is_demo = demo_mode if demo_mode is not None else _get_env_demo_mode()

    if is_demo and memory_type in (MemoryType.PANTRY, MemoryType.TEMPORARY_CONTEXT):
        demo_ttl = timedelta(seconds=_get_env_demo_ttl_seconds())
        return replace(policy, ttl=demo_ttl)

    return policy


def compute_expires_at(
    memory_type: MemoryType,
    created_at: datetime,
    suggested_ttl_hours: Optional[float] = None,
    demo_mode: Optional[bool] = None,
) -> Optional[datetime]:
    """Calculate the absolute UTC expiration timestamp for a memory item.

    Args:
        memory_type: Categorical memory type.
        created_at: Timezone-aware creation timestamp.
        suggested_ttl_hours: Optional caller-suggested TTL in hours.
        demo_mode: Explicit demo flag override. If None, reads from DEMO_MODE env var.

    Returns:
        Timezone-aware UTC expiration datetime, or None if the type does not expire.
    """
    ensure_timezone_aware(created_at)

    policy = get_policy(memory_type, demo_mode=demo_mode)
    if policy.ttl is None:
        return None

    is_demo = demo_mode if demo_mode is not None else _get_env_demo_mode()
    if is_demo:
        demo_seconds = _get_env_demo_ttl_seconds()
        return created_at + timedelta(seconds=demo_seconds)

    if suggested_ttl_hours is not None:
        raw_ttl = timedelta(hours=max(0.0, float(suggested_ttl_hours)))
        max_cap = MAX_TTL_PANTRY if memory_type == MemoryType.PANTRY else MAX_TTL_TEMPORARY_CONTEXT
        effective_ttl = min(raw_ttl, max_cap)
    else:
        effective_ttl = policy.ttl

    return created_at + effective_ttl


def is_protected(memory_type: MemoryType) -> bool:
    """Check if memories of this type are protected from automated eviction."""
    return get_policy(memory_type).protected


def can_auto_supersede(memory_type: MemoryType) -> bool:
    """Check if memories of this type can be automatically superseded by new extractions."""
    return get_policy(memory_type).auto_supersede_allowed


def requires_confirmation(memory_type: MemoryType) -> bool:
    """Check if manual user confirmation is required to modify or supersede this memory."""
    return get_policy(memory_type).requires_confirmation_to_change

