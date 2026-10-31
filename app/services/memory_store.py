"""Memory store service managing candidate ingestion, deduplication, and persistence."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any, Callable, Optional

from app.domain.models import (
    CandidateMemory,
    Memory,
    MemorySource,
    MemoryStatus,
    MemoryType,
    User,
    Visibility,
    utc_now,
)
from app.domain.privacy import redact_sensitive
from app.infra import config
from app.services.lifecycle import Lifecycle, SupersedeResult

logger = logging.getLogger(__name__)

# Configurable minimum confidence threshold
MIN_STORE_CONFIDENCE: float = float(getattr(config, "MIN_STORE_CONFIDENCE", 0.5))


def compute_expires_at(
    memory_type: MemoryType,
    suggested_ttl_hours: Optional[int],
    now: datetime,
) -> Optional[datetime]:
    """Calculate the expiration datetime based on memory type and suggested TTL."""
    if memory_type in (MemoryType.ALLERGY, MemoryType.PREFERENCE, MemoryType.MEAL_OUTCOME):
        return None
    if memory_type == MemoryType.PANTRY:
        hours = suggested_ttl_hours if suggested_ttl_hours is not None else 336  # 14 days
        return now + timedelta(hours=hours)
    if memory_type == MemoryType.TEMPORARY_CONTEXT:
        hours = suggested_ttl_hours if suggested_ttl_hours is not None else 24   # 1 day
        return now + timedelta(hours=hours)
    return None


def is_protected(memory_type: MemoryType) -> bool:
    """Return whether memories of this type are protected from automatic deletion."""
    return memory_type == MemoryType.ALLERGY


def normalize_dedupe_key(mem_type: MemoryType, structured: dict[str, Any], text: str) -> str:
    """Derive a normalized deduplication key from memory type and structured metadata."""
    type_str = mem_type.value if hasattr(mem_type, "value") else str(mem_type)
    if mem_type == MemoryType.ALLERGY:
        allergen = structured.get("allergen") or text
        return f"allergy:{str(allergen).strip().lower()}"
    if mem_type == MemoryType.PREFERENCE:
        item = structured.get("item", "")
        kind = structured.get("kind", "")
        if item:
            return f"preference:{str(item).strip().lower()}:{str(kind).strip().lower()}"
    if mem_type == MemoryType.PANTRY:
        item = structured.get("item") or text
        return f"pantry:{str(item).strip().lower()}"
    if mem_type == MemoryType.TEMPORARY_CONTEXT:
        ctx = structured.get("context") or text
        return f"temporary_context:{str(ctx).strip().lower()}"
    return f"{type_str}:{text.strip().lower()}"


@dataclass
class PendingChange:
    """Candidate memory requiring explicit human confirmation before updating an existing memory."""
    candidate: CandidateMemory
    target_memory: Memory
    question: str


@dataclass
class AmbiguousCorrection:
    """Candidate memory that matched multiple potential targets without a clear winner."""
    candidate: CandidateMemory
    alternatives: list[Memory]


@dataclass
class SkippedCandidate:
    """Candidate memory that was not stored along with the operational reason."""
    candidate: CandidateMemory
    reason: str  # "memory_disabled" | "blocked_sensitive" | "low_confidence" | "empty" | "error"
    details: Optional[str] = None


@dataclass
class StoreResult:
    """Result of processing and persisting a batch of candidate memories."""
    created: list[Memory] = field(default_factory=list)
    superseded: list[SupersedeResult] = field(default_factory=list)
    duplicates_skipped: list[str] = field(default_factory=list)
    needs_confirmation: list[PendingChange] = field(default_factory=list)
    ambiguous_corrections: list[AmbiguousCorrection] = field(default_factory=list)
    skipped: list[SkippedCandidate] = field(default_factory=list)


class MemoryStore:
    """Service governing memory ingestion, redaction, deduplication, and persistence."""

    def __init__(
        self,
        repository: Any,
        lifecycle: Lifecycle,
        user_lookup: Callable[[str], Optional[User]],
        now_fn: Callable[[], datetime] = utc_now,
        min_confidence: Optional[float] = None,
    ) -> None:
        """Initialize MemoryStore with injected repository, lifecycle service, and dependencies."""
        self.repository = repository
        self.lifecycle = lifecycle
        self.user_lookup = user_lookup
        self.now_fn = now_fn
        self.min_confidence = (
            min_confidence if min_confidence is not None else MIN_STORE_CONFIDENCE
        )

    def _build_memory(
        self,
        candidate: CandidateMemory,
        user_id: str,
        session_id: str,
        source_message_id: Optional[str],
        text: str,
        dedupe_key: str,
        now: datetime,
    ) -> Memory:
        """Construct a valid Memory domain object respecting lifecycle and allergy policies."""
        expires_at = compute_expires_at(candidate.type, candidate.suggested_ttl_hours, now)
        protected = is_protected(candidate.type)

        if candidate.type == MemoryType.ALLERGY:
            mem = Memory.model_construct(
                user_id=user_id,
                session_id=session_id,
                source_message_id=source_message_id,
                type=MemoryType.ALLERGY,
                text=text,
                structured=dict(candidate.structured),
                tags=list(candidate.tags),
                source=MemorySource.USER,
                visibility=Visibility.PRIVATE,
                confidence=candidate.confidence,
                protected=True,
                expires_at=None,
                created_at=now,
                updated_at=now,
                status=MemoryStatus.ACTIVE,
            )
            object.__setattr__(mem, "dedupe_key", dedupe_key)
            return mem

        mem = Memory(
            user_id=user_id,
            session_id=session_id,
            source_message_id=source_message_id,
            type=candidate.type,
            text=text,
            structured=dict(candidate.structured),
            tags=list(candidate.tags),
            source=MemorySource.USER,
            visibility=Visibility.PRIVATE,
            confidence=candidate.confidence,
            protected=protected,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
            status=MemoryStatus.ACTIVE,
        )
        object.__setattr__(mem, "dedupe_key", dedupe_key)
        return mem

    def store_candidates(
        self,
        user_id: str,
        session_id: str,
        source_message_id: Optional[str],
        candidates: list[CandidateMemory],
        now: Optional[datetime] = None,
    ) -> StoreResult:
        """Ingest, redact, deduplicate, and persist candidate memories for a user turn."""
        effective_now = now or self.now_fn()
        result = StoreResult()

        # 1. Check user settings memory_enabled
        user = self.user_lookup(user_id)
        if user is not None and hasattr(user, "settings") and not user.settings.memory_enabled:
            for cand in candidates:
                result.skipped.append(
                    SkippedCandidate(candidate=cand, reason="memory_disabled")
                )
            return result

        for candidate in candidates:
            try:
                # Basic empty check
                if not candidate.text or not candidate.text.strip():
                    result.skipped.append(
                        SkippedCandidate(candidate=candidate, reason="empty")
                    )
                    continue

                # 2. Redact sensitive content
                redaction = redact_sensitive(candidate.text)
                if redaction.blocked:
                    result.skipped.append(
                        SkippedCandidate(candidate=candidate, reason="blocked_sensitive")
                    )
                    continue
                sanitized_text = redaction.text

                # 3. Check extraction confidence (allergies always stored)
                is_allergy = candidate.type == MemoryType.ALLERGY
                if not is_allergy and candidate.confidence < self.min_confidence:
                    result.skipped.append(
                        SkippedCandidate(candidate=candidate, reason="low_confidence")
                    )
                    continue

                # 4. Deduplication
                dedupe_key = normalize_dedupe_key(
                    candidate.type, candidate.structured, sanitized_text
                )
                existing_dupes = self.repository.find_duplicate_candidates(
                    user_id=user_id,
                    type=candidate.type,
                    normalized_key=dedupe_key,
                    now=effective_now,
                )
                if existing_dupes:
                    dupe_id = str(existing_dupes[0].get("_id", existing_dupes[0].get("id")))
                    self.repository.update_fields(
                        memory_id=dupe_id,
                        user_id=user_id,
                        fields={"updated_at": effective_now, "last_used_at": effective_now},
                    )
                    result.duplicates_skipped.append(dupe_id)
                    continue

                # 5. Correction detection
                has_explicit_correction = bool(candidate.is_correction_of_text)
                is_polarity_conflict = False
                if candidate.type == MemoryType.PREFERENCE:
                    # Check opposite preference kind (e.g. like vs dislike for same item)
                    item = candidate.structured.get("item", "")
                    current_kind = candidate.structured.get("kind", "")
                    opposite_kind = "dislike" if current_kind == "like" else "like"
                    opposite_key = f"preference:{str(item).strip().lower()}:{opposite_kind}"
                    opposite_matches = self.repository.find_duplicate_candidates(
                        user_id=user_id,
                        type=candidate.type,
                        normalized_key=opposite_key,
                        now=effective_now,
                    )
                    if opposite_matches:
                        is_polarity_conflict = True

                if has_explicit_correction or is_polarity_conflict:
                    resolution = self.lifecycle.find_correction_target(
                        user_id=user_id,
                        candidate=candidate,
                        now=effective_now,
                    )
                    if resolution.status == "single" and resolution.target:
                        target = resolution.target
                        if target.type == MemoryType.ALLERGY:
                            result.needs_confirmation.append(
                                PendingChange(
                                    candidate=candidate,
                                    target_memory=target,
                                    question=f"Update your allergy from '{target.text}' to '{sanitized_text}'?",
                                )
                            )
                            continue
                        else:
                            new_mem = self._build_memory(
                                candidate=candidate,
                                user_id=user_id,
                                session_id=session_id,
                                source_message_id=source_message_id,
                                text=sanitized_text,
                                dedupe_key=dedupe_key,
                                now=effective_now,
                            )
                            sup_res = self.lifecycle.supersede(
                                user_id=user_id,
                                old_memory_id=target.id,
                                new_memory=new_mem,
                                confirmed=False,
                                now=effective_now,
                            )
                            if sup_res.status == "superseded":
                                result.superseded.append(sup_res)
                                result.created.append(new_mem)
                                continue
                            elif sup_res.status == "needs_confirmation":
                                result.needs_confirmation.append(
                                    PendingChange(
                                        candidate=candidate,
                                        target_memory=target,
                                        question=f"Update memory from '{target.text}' to '{sanitized_text}'?",
                                    )
                                )
                                continue
                    elif resolution.status == "ambiguous":
                        new_mem = self._build_memory(
                            candidate=candidate,
                            user_id=user_id,
                            session_id=session_id,
                            source_message_id=source_message_id,
                            text=sanitized_text,
                            dedupe_key=dedupe_key,
                            now=effective_now,
                        )
                        self.repository.insert_memory(new_mem)
                        result.created.append(new_mem)
                        result.ambiguous_corrections.append(
                            AmbiguousCorrection(
                                candidate=candidate,
                                alternatives=resolution.alternatives,
                            )
                        )
                        continue

                # 6. Standard new memory persistence
                new_mem = self._build_memory(
                    candidate=candidate,
                    user_id=user_id,
                    session_id=session_id,
                    source_message_id=source_message_id,
                    text=sanitized_text,
                    dedupe_key=dedupe_key,
                    now=effective_now,
                )
                self.repository.insert_memory(new_mem)
                result.created.append(new_mem)

            except Exception as exc:
                logger.warning(
                    "Error processing candidate memory for user_id=%s, type=%s: %s",
                    user_id,
                    candidate.type,
                    exc,
                )
                result.skipped.append(
                    SkippedCandidate(
                        candidate=candidate,
                        reason="error",
                        details=str(exc),
                    )
                )

        # Log completion at info level without disclosing sensitive text
        logger.info(
            "MemoryStore processed candidates for user_id=%s: created=%d, superseded=%d, dupes=%d, pending=%d, skipped=%d",
            user_id,
            len(result.created),
            len(result.superseded),
            len(result.duplicates_skipped),
            len(result.needs_confirmation),
            len(result.skipped),
        )
        return result

    def confirm_pending(
        self,
        user_id: str,
        pending: PendingChange,
        session_id: str = "confirmed_session",
        source_message_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> SupersedeResult:
        """Apply a pending change confirmed by the user."""
        effective_now = now or self.now_fn()
        dedupe_key = normalize_dedupe_key(
            pending.candidate.type,
            pending.candidate.structured,
            pending.candidate.text,
        )
        new_mem = self._build_memory(
            candidate=pending.candidate,
            user_id=user_id,
            session_id=session_id,
            source_message_id=source_message_id,
            text=pending.candidate.text,
            dedupe_key=dedupe_key,
            now=effective_now,
        )
        return self.lifecycle.supersede(
            user_id=user_id,
            old_memory_id=pending.target_memory.id,
            new_memory=new_mem,
            confirmed=True,
            now=effective_now,
        )
