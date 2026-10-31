"""Base repository exceptions, error inspectors, and pipeline builders."""

from datetime import datetime, timezone
import logging
from typing import Any, Optional
from pymongo.errors import ExecutionTimeout, NetworkTimeout

from app.domain.models import utc_now
from app.infra.providers.base import VectorStrategy

logger = logging.getLogger(__name__)


class VectorIndexNotReadyError(Exception):
    """Raised when the vector search index does not exist or is not ready."""
    pass


class RateLimitError(Exception):
    """Raised when an operation encounters rate limiting or transient timeouts."""
    pass


def is_rate_limit_error(exc: Exception) -> bool:
    """Determine whether an exception indicates a rate-limit or timeout condition."""
    if isinstance(exc, (ExecutionTimeout, NetworkTimeout)):
        return True
    msg = str(exc).lower()
    if any(keyword in msg for keyword in ("rate limit", "429", "quota", "toomanyrequests", "rate_limit")):
        return True
    code = getattr(exc, "code", None)
    if code in (429, 50):  # 50 is ExceededTimeLimit in MongoDB
        return True
    return False


def ensure_utc_datetimes(
    doc: dict[str, Any],
    fields: tuple[str, ...] = (
        "created_at",
        "updated_at",
        "expires_at",
        "last_used_at",
        "deleted_at",
        "first_message_time",
        "last_message_time",
    ),
) -> dict[str, Any]:
    """Ensure that datetime fields on a document are timezone-aware in UTC."""
    for field in fields:
        val = doc.get(field)
        if isinstance(val, datetime) and val.tzinfo is None:
            doc[field] = val.replace(tzinfo=timezone.utc)
    return doc


def build_vector_search_pipeline(
    strategy: VectorStrategy,
    query_text: str,
    user_id: str,
    limit: int = 10,
    memory_types: Optional[list[str]] = None,
    statuses: tuple[str, ...] = ("active",),
    num_candidates: Optional[int] = None,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Build the MongoDB aggregation pipeline for vector search.

    Pure function constructing pre-filters, over-fetch vector search,
    expiration filtering, vector score projection, and final limit trimming.
    """
    effective_candidates = (
        num_candidates if num_candidates is not None else strategy.num_candidates
    )
    overfetch_limit = min(limit * 3, effective_candidates)
    if overfetch_limit < limit:
        overfetch_limit = limit

    filters: dict[str, Any] = {"user_id": user_id}
    if statuses:
        filters["status"] = list(statuses) if len(statuses) > 1 else statuses[0]
    if memory_types:
        raw_types = [t.value if hasattr(t, "value") else str(t) for t in memory_types]
        filters["type"] = raw_types if len(raw_types) > 1 else raw_types[0]

    vector_search_stage = strategy.build_vector_search_stage(
        query_text=query_text,
        filters=filters,
        limit=overfetch_limit,
        num_candidates=effective_candidates,
    )

    current_time = now if now is not None else utc_now()
    match_stage = {
        "$match": {
            "$or": [
                {"expires_at": None},
                {"expires_at": {"$exists": False}},
                {"expires_at": {"$gt": current_time}},
            ]
        }
    }

    project_stage = {
        "$project": {
            "embedding": 0,
            "_score": {"$meta": "vectorSearchScore"},
        }
    }

    limit_stage = {"$limit": limit}

    return [vector_search_stage, match_stage, project_stage, limit_stage]

