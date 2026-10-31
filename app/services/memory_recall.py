"""Memory recall service orchestrating vector retrieval, allergies, and lifecycle filtering."""

from datetime import datetime
import logging
from typing import Any, Callable, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import (
    Memory,
    MemoryStatus,
    MemoryType,
    RecalledMemory,
    ScoreBreakdown,
    User,
    utc_now,
)
from app.infra.memory_repository import VectorIndexNotReadyError

logger = logging.getLogger(__name__)


def _dict_to_memory(doc: dict[str, Any]) -> Memory:
    """Safely convert a database document dictionary to a Memory domain model."""
    doc_copy = dict(doc)
    doc_id = str(doc_copy.pop("_id", doc_copy.get("id", "")))
    doc_copy["id"] = doc_id
    raw_type = doc_copy.get("type")
    if isinstance(raw_type, str):
        try:
            doc_copy["type"] = MemoryType(raw_type)
        except ValueError:
            pass

    # Allergy memories use model_construct to bypass pydantic validator recursion on assignment
    if doc_copy.get("type") == MemoryType.ALLERGY:
        doc_copy["protected"] = True
        doc_copy["expires_at"] = None
        return Memory.model_construct(**doc_copy)

    return Memory(**doc_copy)


class RecallResult(BaseModel):
    """Container for recalled memories, always-applied constraints, and metadata."""
    model_config = ConfigDict(populate_by_name=True)

    recalled: list[RecalledMemory] = Field(
        default_factory=list,
        description="Ranked memories retrieved via semantic vector search.",
    )
    always_applied: list[Memory] = Field(
        default_factory=list,
        description="Always-applied memories (such as active allergies) regardless of similarity.",
    )
    matched_filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Filters applied during retrieval.",
    )
    warning: Optional[str] = Field(
        default=None,
        description="Warning notice if retrieval was degraded or index was unready.",
    )


def default_rerank(items: list[RecalledMemory]) -> list[RecalledMemory]:
    """Default identity ranking sorting candidates descending by similarity score."""
    return sorted(items, key=lambda rm: rm.score.similarity, reverse=True)


class MemoryRecall:
    """Service retrieving relevant memories and applying always-on culinary guardrails."""

    def __init__(
        self,
        repository: Any,
        rerank: Optional[Callable[[list[RecalledMemory]], list[RecalledMemory]]] = None,
        user_lookup: Optional[Callable[[str], Optional[User]]] = None,
    ) -> None:
        """Initialize recall service with injected repository, optional reranker, and user lookup."""
        self.repository = repository
        self.rerank = rerank or default_rerank
        self.user_lookup = user_lookup

    def recall(
        self,
        user_id: str,
        query_text: str,
        limit: int = 5,
        memory_types: Optional[list[str]] = None,
    ) -> RecallResult:
        """Recall relevant memories for user query with allergy guardrails and safety exclusions."""
        # 1. Respect user memory_enabled setting
        if self.user_lookup is not None:
            user = self.user_lookup(user_id)
            if user is not None and hasattr(user, "settings") and not user.settings.memory_enabled:
                return RecallResult.model_construct(
                    recalled=[],
                    always_applied=[],
                    matched_filters={"user_id": user_id, "memory_enabled": False},
                    warning=None,
                )

        now = utc_now()
        matched_filters: dict[str, Any] = {
            "user_id": user_id,
            "status": "active",
            "types": memory_types,
        }

        # 2. Always fetch active allergies
        raw_allergies = self.repository.get_active_by_type(user_id=user_id, memory_type="allergy")
        always_applied: list[Memory] = []
        for doc in raw_allergies:
            mem = _dict_to_memory(doc)
            if mem.is_active(now):
                always_applied.append(mem)

        # 3. Vector search candidates
        try:
            raw_candidates = self.repository.vector_search(
                query_text=query_text,
                user_id=user_id,
                limit=limit,
                memory_types=memory_types,
                statuses=("active",),
            )
        except VectorIndexNotReadyError as exc:
            logger.warning("Vector index not ready during recall: %s", exc)
            return RecallResult.model_construct(
                recalled=[],
                always_applied=always_applied,
                matched_filters=matched_filters,
                warning=str(exc),
            )

        # 4. Filter lifecycle states and build RecalledMemory models
        always_applied_ids = {m.id for m in always_applied}
        recalled_candidates: list[RecalledMemory] = []

        for doc in raw_candidates:
            mem = _dict_to_memory(doc)
            if not mem.is_active(now):
                continue
            if mem.id in always_applied_ids:
                continue

            sim_score = float(doc.get("_score", 0.0))
            score_breakdown = ScoreBreakdown(
                similarity=sim_score,
                final_score=sim_score,
            )

            reasons = [
                f"semantic match ({sim_score:.2f})",
                f"type: {mem.type.value if hasattr(mem.type, 'value') else mem.type}",
            ]
            if mem.last_used_at is not None:
                reasons.append("recent use")

            recalled_mem = RecalledMemory.model_construct(
                memory=mem,
                score=score_breakdown,
                reasons=reasons,
                matched_filters=matched_filters,
            )
            recalled_candidates.append(recalled_mem)

        # 5. Apply injected rerank callable and trim to requested limit
        ranked_items = self.rerank(recalled_candidates)
        final_recalled = ranked_items[:limit]

        return RecallResult.model_construct(
            recalled=final_recalled,
            always_applied=always_applied,
            matched_filters=matched_filters,
            warning=None,
        )

    def mark_recalled(self, result: RecallResult) -> None:
        """Mark all recalled and always-applied memory records as used in repository."""
        ids_to_mark: list[str] = []
        for rm in result.recalled:
            if rm.memory.id:
                ids_to_mark.append(rm.memory.id)
        for m in result.always_applied:
            if m.id:
                ids_to_mark.append(m.id)

        unique_ids = list(dict.fromkeys(ids_to_mark))
        if unique_ids:
            self.repository.mark_used(unique_ids)
