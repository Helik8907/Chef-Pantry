"""Offline unit tests for memory lifecycle service."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.domain.models import (
    CandidateMemory,
    Memory,
    MemoryStatus,
    MemoryType,
    MemoryUpdateRequest,
    RecalledMemory,
    ScoreBreakdown,
    utc_now,
)
from app.services.lifecycle import (
    CorrectionResolution,
    ForgetResult,
    Lifecycle,
    SupersedeResult,
)
from app.services.memory_recall import RecallResult


class FakeLifecycleRepository:
    """In-memory double for testing Lifecycle operations."""

    def __init__(self) -> None:
        self.memories: dict[str, dict[str, Any]] = {}
        self.next_id: int = 1

    def insert_memory(self, memory: Memory) -> str:
        doc = memory.model_dump(by_alias=True)
        if not doc.get("_id"):
            doc["_id"] = f"mem_{self.next_id}"
            self.next_id += 1
        doc_id = str(doc["_id"])
        doc["embedding"] = [0.1] * 10  # simulate mock embedding
        self.memories[doc_id] = doc
        return doc_id

    def get_memory_by_id_scoped(self, memory_id: str, user_id: str) -> Optional[dict[str, Any]]:
        doc = self.memories.get(memory_id)
        if doc and doc.get("user_id") == user_id:
            return dict(doc)
        return None

    def update_fields(self, memory_id: str, user_id: str, fields: dict[str, Any]) -> bool:
        doc = self.memories.get(memory_id)
        if doc and doc.get("user_id") == user_id:
            doc.update(fields)
            doc["updated_at"] = utc_now()
            return True
        return False

    def link_supersede(self, old_id: str, new_id: str, user_id: str) -> bool:
        old_doc = self.memories.get(old_id)
        new_doc = self.memories.get(new_id)
        if old_doc and new_doc and old_doc.get("user_id") == user_id:
            old_doc["status"] = MemoryStatus.SUPERSEDED.value
            old_doc["superseded_by"] = new_id
            new_doc["supersedes"] = old_id
            return True
        return False

    def soft_delete(self, memory_id: str, user_id: str, now: Optional[datetime] = None) -> bool:
        doc = self.memories.get(memory_id)
        if doc and doc.get("user_id") == user_id:
            doc["status"] = MemoryStatus.DELETED.value
            doc["deleted_at"] = now or utc_now()
            doc.pop("embedding", None)
            return True
        return False

    def hard_delete(self, memory_id: str, user_id: str) -> bool:
        doc = self.memories.get(memory_id)
        if doc and doc.get("user_id") == user_id:
            del self.memories[memory_id]
            return True
        return False

    def find_expired(self, user_id: Optional[str] = None, now: Optional[datetime] = None) -> list[dict[str, Any]]:
        ts = now or utc_now()
        results = []
        for doc in self.memories.values():
            if user_id and doc.get("user_id") != user_id:
                continue
            if doc.get("status") == "active" and doc.get("expires_at"):
                if doc["expires_at"] <= ts:
                    results.append(dict(doc))
        return results

    def list_memories(self, user_id: str, filters: Optional[dict[str, Any]] = None, limit: int = 50) -> list[dict[str, Any]]:
        results = []
        for doc in self.memories.values():
            if doc.get("user_id") != user_id:
                continue
            matches = True
            if filters:
                if filters.get("status") and doc.get("status") != filters["status"]:
                    matches = False
                if "$gte" in str(filters.get("expires_at", {})):
                    min_exp = filters["expires_at"]["$gte"]
                    max_exp = filters["expires_at"]["$lte"]
                    doc_exp = doc.get("expires_at")
                    if not doc_exp or not (min_exp <= doc_exp <= max_exp):
                        matches = False
            if matches:
                results.append(dict(doc))
        return results[:limit]


class StubRecall:
    """Stub recall for Lifecycle testing."""
    def __init__(self, recall_result: Optional[RecallResult] = None) -> None:
        self.recall_result = recall_result or RecallResult()

    def recall(self, user_id: str, query_text: str, memory_types: Optional[list[str]] = None) -> RecallResult:
        return self.recall_result


def test_soft_delete_and_hard_delete():
    """forget() soft-deletes removing embedding and setting deleted_at, hard=True deletes."""
    repo = FakeLifecycleRepository()
    lifecycle = Lifecycle(repository=repo, recall=StubRecall())

    mem = Memory(user_id="user_1", type=MemoryType.PREFERENCE, text="Loves garlic")
    mem_id = repo.insert_memory(mem)
    assert "embedding" in repo.memories[mem_id]

    fixed_now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    # 1. Soft delete
    res_soft = lifecycle.forget(user_id="user_1", memory_id=mem_id, hard=False, now=fixed_now)
    assert res_soft.status == "deleted"
    assert repo.memories[mem_id]["status"] == "deleted"
    assert repo.memories[mem_id]["deleted_at"] == fixed_now
    assert "embedding" not in repo.memories[mem_id]

    # 2. Hard delete
    res_hard = lifecycle.forget(user_id="user_1", memory_id=mem_id, hard=True, now=fixed_now)
    assert res_hard.status == "deleted"
    assert mem_id not in repo.memories


def test_forget_allergy_always_works():
    """User-initiated forget must succeed even on protected allergies."""
    repo = FakeLifecycleRepository()
    lifecycle = Lifecycle(repository=repo, recall=StubRecall())

    allergy = Memory.model_construct(
        user_id="user_1",
        type=MemoryType.ALLERGY,
        text="Severe peanut allergy",
        protected=True,
        expires_at=None,
        status=MemoryStatus.ACTIVE,
    )
    allergy_id = repo.insert_memory(allergy)
    assert repo.memories[allergy_id]["protected"] is True

    res = lifecycle.forget(user_id="user_1", memory_id=allergy_id, hard=False)
    assert res.status == "deleted"
    assert repo.memories[allergy_id]["status"] == "deleted"


def test_supersede_preserves_old_text_and_links():
    """supersede creates reciprocal links, preserves old document text, and updates statuses."""
    repo = FakeLifecycleRepository()
    lifecycle = Lifecycle(repository=repo, recall=StubRecall())

    old_mem = Memory(user_id="user_1", type=MemoryType.PREFERENCE, text="Dislikes cilantro")
    old_id = repo.insert_memory(old_mem)

    new_mem = Memory(user_id="user_1", type=MemoryType.PREFERENCE, text="Now loves fresh cilantro in salsa")
    res = lifecycle.supersede(user_id="user_1", old_memory_id=old_id, new_memory=new_mem)

    assert res.status == "superseded"
    assert res.old_id == old_id
    assert res.new_id is not None

    # Verify old text remains unchanged
    assert repo.memories[old_id]["text"] == "Dislikes cilantro"
    assert repo.memories[old_id]["status"] == "superseded"
    assert repo.memories[old_id]["superseded_by"] == res.new_id
    assert repo.memories[res.new_id]["supersedes"] == old_id


def test_supersede_allergy_requires_confirmation():
    """Automatic supersede on allergy returns needs_confirmation unless confirmed=True."""
    repo = FakeLifecycleRepository()
    lifecycle = Lifecycle(repository=repo, recall=StubRecall())

    old_allergy = Memory.model_construct(
        user_id="user_1",
        type=MemoryType.ALLERGY,
        text="Allergic to shellfish",
        protected=True,
        expires_at=None,
        status=MemoryStatus.ACTIVE,
    )
    old_id = repo.insert_memory(old_allergy)

    new_allergy = Memory.model_construct(
        user_id="user_1",
        type=MemoryType.ALLERGY,
        text="Allergic only to shrimp",
        protected=True,
        expires_at=None,
        status=MemoryStatus.ACTIVE,
    )
    res_unconfirmed = lifecycle.supersede(user_id="user_1", old_memory_id=old_id, new_memory=new_allergy, confirmed=False)

    assert res_unconfirmed.status == "needs_confirmation"
    assert repo.memories[old_id]["status"] == "active"  # Untouched

    # Now apply with confirmed=True
    res_confirmed = lifecycle.supersede(user_id="user_1", old_memory_id=old_id, new_memory=new_allergy, confirmed=True)
    assert res_confirmed.status == "superseded"
    assert repo.memories[old_id]["status"] == "superseded"


def test_forget_cleans_dangling_references():
    """forget cleans reciprocal supersede links so inspector does not encounter dangling IDs."""
    repo = FakeLifecycleRepository()
    lifecycle = Lifecycle(repository=repo, recall=StubRecall())

    mem_v1 = Memory(user_id="user_1", type=MemoryType.PREFERENCE, text="Version 1")
    id_v1 = repo.insert_memory(mem_v1)
    mem_v2 = Memory(user_id="user_1", type=MemoryType.PREFERENCE, text="Version 2")
    res = lifecycle.supersede(user_id="user_1", old_memory_id=id_v1, new_memory=mem_v2)
    id_v2 = res.new_id

    assert repo.memories[id_v1]["superseded_by"] == id_v2
    assert repo.memories[id_v2]["supersedes"] == id_v1

    # Forget V2
    lifecycle.forget(user_id="user_1", memory_id=id_v2, hard=True)
    assert repo.memories[id_v1]["superseded_by"] is None


def test_revise_creates_new_version():
    """revise creates a new version carrying updated fields and supersedes old."""
    repo = FakeLifecycleRepository()
    lifecycle = Lifecycle(repository=repo, recall=StubRecall())

    mem = Memory(user_id="user_1", type=MemoryType.PREFERENCE, text="Likes medium-rare steak", tags=["steak"])
    mem_id = repo.insert_memory(mem)

    update = MemoryUpdateRequest(text="Prefers medium steak", tags=["steak", "beef"])
    res = lifecycle.revise(user_id="user_1", memory_id=mem_id, update=update)

    assert res.status == "superseded"
    assert repo.memories[res.new_id]["text"] == "Prefers medium steak"
    assert repo.memories[res.new_id]["tags"] == ["steak", "beef"]
    assert repo.memories[mem_id]["status"] == "superseded"


def test_expire_now_and_purge_expired():
    """expire_now sets expires_at to now, purge_expired deletes only expired items."""
    repo = FakeLifecycleRepository()
    fixed_now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    lifecycle = Lifecycle(repository=repo, recall=StubRecall(), now_fn=lambda: fixed_now)

    active_mem = Memory(user_id="user_1", type=MemoryType.PANTRY, text="Milk in fridge")
    active_id = repo.insert_memory(active_mem)

    temp_mem = Memory(user_id="user_1", type=MemoryType.TEMPORARY_CONTEXT, text="Dinner party tonight")
    temp_id = repo.insert_memory(temp_mem)

    lifecycle.expire_now(user_id="user_1", memory_id=temp_id, now=fixed_now)
    assert repo.memories[temp_id]["expires_at"] == fixed_now

    purged = lifecycle.purge_expired(user_id="user_1", now=fixed_now)
    assert purged == 1
    assert temp_id not in repo.memories
    assert active_id in repo.memories


def test_user_scoping_security():
    """Operations against a memory belonging to another user must fail safely."""
    repo = FakeLifecycleRepository()
    lifecycle = Lifecycle(repository=repo, recall=StubRecall())

    mem_alice = Memory(user_id="alice", type=MemoryType.PREFERENCE, text="Alice's secret recipe")
    id_alice = repo.insert_memory(mem_alice)

    # Bob attempts to access / delete / revise Alice's memory
    res_forget = lifecycle.forget(user_id="bob", memory_id=id_alice)
    assert res_forget.status == "not_found"

    res_supersede = lifecycle.supersede(
        user_id="bob",
        old_memory_id=id_alice,
        new_memory=Memory(user_id="bob", type=MemoryType.PREFERENCE, text="Bob's memory"),
    )
    assert res_supersede.status == "not_found"

    res_revise = lifecycle.revise(
        user_id="bob",
        memory_id=id_alice,
        update=MemoryUpdateRequest(text="Malicious overwrite"),
    )
    assert res_revise.status == "not_found"
    assert repo.memories[id_alice]["text"] == "Alice's secret recipe"


def test_find_correction_target_single_vs_ambiguous_vs_none():
    """Verify threshold and margin gating for correction target resolution."""
    repo = FakeLifecycleRepository()
    fixed_now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)

    mem_lead = Memory(user_id="user_1", type=MemoryType.PREFERENCE, text="Loves hot spicy food")
    mem_runner_up = Memory(user_id="user_1", type=MemoryType.PREFERENCE, text="Prefers mild food")

    # 1. Single target: top score 0.88, runner-up 0.76 (diff 0.12 >= 0.08)
    recall_single = RecallResult(
        recalled=[
            RecalledMemory(
                memory=mem_lead,
                score=ScoreBreakdown(similarity=0.88, final_score=0.88),
            ),
            RecalledMemory(
                memory=mem_runner_up,
                score=ScoreBreakdown(similarity=0.76, final_score=0.76),
            ),
        ]
    )
    lifecycle = Lifecycle(repository=repo, recall=StubRecall(recall_single))
    candidate = CandidateMemory(
        type=MemoryType.PREFERENCE,
        text="Actually I cannot eat spicy food anymore",
        is_correction_of_text="Loves hot spicy food",
    )
    res_single = lifecycle.find_correction_target("user_1", candidate, now=fixed_now)
    assert res_single.status == "single"
    assert res_single.target is not None
    assert res_single.target.text == "Loves hot spicy food"

    # 2. Ambiguous target: top score 0.82, runner-up 0.80 (diff 0.02 < 0.08)
    recall_ambig = RecallResult(
        recalled=[
            RecalledMemory(
                memory=mem_lead,
                score=ScoreBreakdown(similarity=0.82, final_score=0.82),
            ),
            RecalledMemory(
                memory=mem_runner_up,
                score=ScoreBreakdown(similarity=0.80, final_score=0.80),
            ),
        ]
    )
    lifecycle_ambig = Lifecycle(repository=repo, recall=StubRecall(recall_ambig))
    res_ambig = lifecycle_ambig.find_correction_target("user_1", candidate, now=fixed_now)
    assert res_ambig.status == "ambiguous"
    assert res_ambig.target is None
    assert len(res_ambig.alternatives) == 2

    # 3. None target: top score 0.60 (< 0.75 threshold)
    recall_none = RecallResult(
        recalled=[
            RecalledMemory(
                memory=mem_lead,
                score=ScoreBreakdown(similarity=0.60, final_score=0.60),
            ),
        ]
    )
    lifecycle_none = Lifecycle(repository=repo, recall=StubRecall(recall_none))
    res_none = lifecycle_none.find_correction_target("user_1", candidate, now=fixed_now)
    assert res_none.status == "none"
    assert res_none.target is None

