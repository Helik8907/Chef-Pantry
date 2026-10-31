"""Memory lifecycle service managing superseding, deletion, revision, and expiration."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any, Callable, Optional

from app.domain.models import (
    CandidateMemory,
    Memory,
    MemoryStatus,
    MemoryType,
    MemoryUpdateRequest,
    RecalledMemory,
    utc_now,
)
from app.infra import config

logger = logging.getLogger(__name__)

# Configurable similarity and confidence thresholds with fallbacks
CORRECTION_SIMILARITY_THRESHOLD: float = float(
    getattr(config, "CORRECTION_SIMILARITY_THRESHOLD", 0.75)
)
CORRECTION_MARGIN: float = float(
    getattr(config, "CORRECTION_MARGIN", 0.08)
)


def _doc_to_memory(doc: dict[str, Any]) -> Memory:
    """Convert a database document dictionary to a Memory domain model."""
    doc_copy = dict(doc)
    doc_id = str(doc_copy.pop("_id", doc_copy.get("id", "")))
    doc_copy["id"] = doc_id
    raw_type = doc_copy.get("type")
    if isinstance(raw_type, str):
        try:
            doc_copy["type"] = MemoryType(raw_type)
        except ValueError:
            pass

    if doc_copy.get("type") == MemoryType.ALLERGY or doc_copy.get("type") == "allergy":
        doc_copy["type"] = MemoryType.ALLERGY
        doc_copy["protected"] = True
        doc_copy["expires_at"] = None
        return Memory.model_construct(**doc_copy)

    return Memory(**doc_copy)


@dataclass
class CorrectionResolution:
    """Result of searching for a memory targeted by a correction."""
    status: str  # "none" | "single" | "ambiguous"
    target: Optional[Memory] = None
    alternatives: list[Memory] = field(default_factory=list)


@dataclass
class SupersedeResult:
    """Result of superseding an existing memory."""
    status: str  # "superseded" | "needs_confirmation" | "not_allowed" | "not_found"
    old_id: Optional[str] = None
    new_id: Optional[str] = None
    message: str = ""


@dataclass
class ForgetResult:
    """Result of forgetting (deleting) a memory."""
    status: str  # "deleted" | "not_found"
    memory_id: str
    hard: bool = False
    message: str = ""


class Lifecycle:
    """Service managing memory revisions, superseding, expiration, and deletions."""

    def __init__(
        self,
        repository: Any,
        recall: Any,
        now_fn: Callable[[], datetime] = utc_now,
        similarity_threshold: Optional[float] = None,
        margin: Optional[float] = None,
    ) -> None:
        """Initialize Lifecycle service with dependencies and deterministic clock."""
        self.repository = repository
        self.recall = recall
        self.now_fn = now_fn
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else CORRECTION_SIMILARITY_THRESHOLD
        )
        self.margin = margin if margin is not None else CORRECTION_MARGIN

    def find_correction_target(
        self,
        user_id: str,
        candidate: CandidateMemory,
        now: Optional[datetime] = None,
    ) -> CorrectionResolution:
        """Identify if a candidate memory targets an existing memory for correction.

        Uses candidate.is_correction_of_text (falling back to candidate.text) and
        vector search scoped to the user, prioritizing the same memory type.
        """
        search_text = candidate.is_correction_of_text or candidate.text
        type_val = (
            candidate.type.value if hasattr(candidate.type, "value") else str(candidate.type)
        )

        recall_res = self.recall.recall(
            user_id=user_id,
            query_text=search_text,
            memory_types=[type_val],
        )

        candidates: list[tuple[Memory, float]] = []

        # 1. Process recalled candidates with similarity scores
        if hasattr(recall_res, "recalled"):
            for rm in recall_res.recalled:
                score = rm.score.similarity if hasattr(rm, "score") else 0.0
                candidates.append((rm.memory, score))

        # 2. If candidate is allergy and recalled was empty, check always_applied
        if not candidates and hasattr(recall_res, "always_applied") and candidate.type == MemoryType.ALLERGY:
            for mem in recall_res.always_applied:
                # Text match heuristic for allergies
                if candidate.is_correction_of_text and candidate.is_correction_of_text.lower() in mem.text.lower():
                    candidates.append((mem, 1.0))
                elif candidate.structured.get("allergen") and candidate.structured.get("allergen") == mem.structured.get("allergen"):
                    candidates.append((mem, 0.95))

        if not candidates:
            return CorrectionResolution(status="none", target=None, alternatives=[])

        # Sort descending by similarity
        candidates.sort(key=lambda pair: pair[1], reverse=True)

        # Filter by threshold
        qualifying = [pair for pair in candidates if pair[1] >= self.similarity_threshold]
        if not qualifying:
            return CorrectionResolution(status="none", target=None, alternatives=[])

        if len(qualifying) == 1:
            top_mem, top_score = qualifying[0]
            # Check runner-up across all candidates
            if len(candidates) == 1:
                return CorrectionResolution(status="single", target=top_mem, alternatives=[])
            runner_up_score = candidates[1][1]
            if (top_score - runner_up_score) >= self.margin:
                return CorrectionResolution(status="single", target=top_mem, alternatives=[])
            else:
                alts = [pair[0] for pair in candidates[:3]]
                return CorrectionResolution(status="ambiguous", target=None, alternatives=alts)

        # Multiple qualifying above threshold
        first_mem, first_score = qualifying[0]
        second_score = qualifying[1][1]
        if (first_score - second_score) >= self.margin:
            return CorrectionResolution(status="single", target=first_mem, alternatives=[])

        return CorrectionResolution(
            status="ambiguous",
            target=None,
            alternatives=[pair[0] for pair in qualifying],
        )

    def supersede(
        self,
        user_id: str,
        old_memory_id: str,
        new_memory: Memory,
        confirmed: bool = False,
        now: Optional[datetime] = None,
    ) -> SupersedeResult:
        """Supersede an existing memory with a new version without mutating old text.

        If the target is a protected allergy and confirmed is False, returns
        'needs_confirmation' without modifying any documents.
        """
        old_doc = self.repository.get_memory_by_id_scoped(old_memory_id, user_id)
        if not old_doc:
            return SupersedeResult(
                status="not_found",
                old_id=old_memory_id,
                new_id=None,
                message=f"Memory '{old_memory_id}' not found for user.",
            )

        # Allergy or protected policy check
        is_allergy = (
            old_doc.get("type") == MemoryType.ALLERGY.value
            or old_doc.get("type") == MemoryType.ALLERGY
            or old_doc.get("protected") is True
        )
        if is_allergy and not confirmed:
            return SupersedeResult(
                status="needs_confirmation",
                old_id=old_memory_id,
                new_id=None,
                message="Updating or superseding an allergy requires explicit user confirmation.",
            )

        # Ensure user_id scoping on new memory safely without triggering Pydantic validator recursion
        if new_memory.user_id != user_id:
            object.__setattr__(new_memory, "user_id", user_id)
        new_id = self.repository.insert_memory(new_memory)
        self.repository.link_supersede(old_id=old_memory_id, new_id=new_id, user_id=user_id)

        return SupersedeResult(
            status="superseded",
            old_id=old_memory_id,
            new_id=new_id,
            message="Successfully superseded existing memory.",
        )

    def forget(
        self,
        user_id: str,
        memory_id: str,
        hard: bool = False,
        now: Optional[datetime] = None,
    ) -> ForgetResult:
        """Forget (delete) a memory.

        User-initiated deletion always succeeds, even for protected allergies.
        Maintains referential integrity by cleaning reciprocal supersede links.
        """
        doc = self.repository.get_memory_by_id_scoped(memory_id, user_id)
        if not doc:
            return ForgetResult(
                status="not_found",
                memory_id=memory_id,
                hard=hard,
                message="Memory not found.",
            )

        # Clean dangling references
        if doc.get("supersedes"):
            self.repository.update_fields(
                memory_id=doc["supersedes"],
                user_id=user_id,
                fields={"superseded_by": None},
            )
        if doc.get("superseded_by"):
            self.repository.update_fields(
                memory_id=doc["superseded_by"],
                user_id=user_id,
                fields={"supersedes": None},
            )

        effective_now = now or self.now_fn()
        if hard:
            self.repository.hard_delete(memory_id=memory_id, user_id=user_id)
        else:
            self.repository.soft_delete(memory_id=memory_id, user_id=user_id, now=effective_now)

        return ForgetResult(
            status="deleted",
            memory_id=memory_id,
            hard=hard,
            message="Memory deleted successfully.",
        )

    def revise(
        self,
        user_id: str,
        memory_id: str,
        update: MemoryUpdateRequest,
        confirmed: bool = False,
        now: Optional[datetime] = None,
    ) -> SupersedeResult:
        """Revise an existing memory by creating a new version and superseding the old one."""
        old_doc = self.repository.get_memory_by_id_scoped(memory_id, user_id)
        if not old_doc:
            return SupersedeResult(
                status="not_found",
                old_id=memory_id,
                new_id=None,
                message="Memory not found.",
            )

        effective_now = now or self.now_fn()
        old_mem = _doc_to_memory(old_doc)

        new_text = update.text if update.text is not None else old_mem.text
        new_structured = (
            update.structured if update.structured is not None else old_mem.structured
        )
        new_tags = update.tags if update.tags is not None else old_mem.tags
        new_expires_at = (
            update.expires_at if update.expires_at is not None else old_mem.expires_at
        )

        new_memory = Memory(
            user_id=user_id,
            type=old_mem.type,
            text=new_text,
            structured=new_structured,
            tags=new_tags,
            source=old_mem.source,
            visibility=old_mem.visibility,
            session_id=old_mem.session_id,
            source_message_id=old_mem.source_message_id,
            confidence=old_mem.confidence,
            expires_at=new_expires_at,
            created_at=effective_now,
            updated_at=effective_now,
            status=MemoryStatus.ACTIVE,
        )

        return self.supersede(
            user_id=user_id,
            old_memory_id=memory_id,
            new_memory=new_memory,
            confirmed=confirmed,
            now=effective_now,
        )

    def expire_now(
        self,
        user_id: str,
        memory_id: str,
        now: Optional[datetime] = None,
    ) -> bool:
        """Demo helper setting expires_at to now so memory immediately leaves recall."""
        effective_now = now or self.now_fn()
        return self.repository.update_fields(
            memory_id=memory_id,
            user_id=user_id,
            fields={"expires_at": effective_now},
        )

    def purge_expired(
        self,
        user_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> int:
        """Demo/maintenance helper permanently removing documents past expires_at."""
        effective_now = now or self.now_fn()
        expired = self.repository.find_expired(user_id=user_id, now=effective_now)
        count = 0
        for doc in expired:
            doc_user = doc.get("user_id") or user_id or ""
            doc_id = str(doc.get("_id", ""))
            if doc_id and doc_user:
                if self.repository.hard_delete(memory_id=doc_id, user_id=doc_user):
                    count += 1
        return count

    def list_expiring(
        self,
        user_id: str,
        within: timedelta,
        now: Optional[datetime] = None,
    ) -> list[Memory]:
        """List active memories expiring within the given timedelta from now."""
        effective_now = now or self.now_fn()
        max_time = effective_now + within
        filters = {
            "status": "active",
            "expires_at": {"$gte": effective_now, "$lte": max_time},
        }
        docs = self.repository.list_memories(user_id=user_id, filters=filters, limit=100)
        return [_doc_to_memory(doc) for doc in docs]
