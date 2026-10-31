"""Offline unit tests for memory store service."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.domain.models import (
    CandidateMemory,
    Memory,
    MemoryStatus,
    MemoryType,
    RecalledMemory,
    ScoreBreakdown,
    User,
    UserSettings,
)
from app.services.lifecycle import Lifecycle
from app.services.memory_recall import RecallResult
from app.services.memory_store import MemoryStore, PendingChange


class FakeStoreRepository:
    """In-memory repository test double for MemoryStore tests."""

    def __init__(self) -> None:
        self.memories: dict[str, dict[str, Any]] = {}
        self.next_id: int = 1

    def insert_memory(self, memory: Memory) -> str:
        doc = memory.model_dump(by_alias=True)
        if not doc.get("_id"):
            doc["_id"] = f"mem_{self.next_id}"
            self.next_id += 1
        doc_id = str(doc["_id"])
        # If dedupe_key was set on memory object, store it in doc
        if hasattr(memory, "dedupe_key"):
            doc["dedupe_key"] = getattr(memory, "dedupe_key")
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
            doc["deleted_at"] = now
            doc.pop("embedding", None)
            return True
        return False

    def hard_delete(self, memory_id: str, user_id: str) -> bool:
        doc = self.memories.get(memory_id)
        if doc and doc.get("user_id") == user_id:
            del self.memories[memory_id]
            return True
        return False

    def find_duplicate_candidates(
        self,
        user_id: str,
        type: Any,
        normalized_key: str,
        now: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        type_val = type.value if hasattr(type, "value") else str(type)
        results = []
        for doc in self.memories.values():
            if doc.get("user_id") == user_id and doc.get("type") == type_val and doc.get("status") == "active":
                if doc.get("dedupe_key") == normalized_key:
                    results.append(dict(doc))
        return results

    def find_expired(self, user_id: Optional[str] = None, now: Optional[datetime] = None) -> list[dict[str, Any]]:
        return []

    def list_memories(self, user_id: str, filters: Optional[dict[str, Any]] = None, limit: int = 50) -> list[dict[str, Any]]:
        return list(self.memories.values())[:limit]


class StubRecall:
    """Stub recall provider for MemoryStore tests."""

    def __init__(self, recall_result: Optional[RecallResult] = None) -> None:
        self.recall_result = recall_result or RecallResult()

    def recall(self, user_id: str, query_text: str, memory_types: Optional[list[str]] = None) -> RecallResult:
        return self.recall_result


def test_memory_enabled_false_stores_nothing():
    """When user settings disable memory retention, all candidates are skipped."""
    repo = FakeStoreRepository()
    recall = StubRecall()
    lifecycle = Lifecycle(repository=repo, recall=recall)

    disabled_user = User(
        user_id="user_disabled",
        display_name="Private User",
        settings=UserSettings(memory_enabled=False),
    )
    store = MemoryStore(
        repository=repo,
        lifecycle=lifecycle,
        user_lookup=lambda uid: disabled_user if uid == "user_disabled" else None,
    )

    cands = [
        CandidateMemory(type=MemoryType.PREFERENCE, text="Loves sushi"),
        CandidateMemory(type=MemoryType.ALLERGY, text="Peanuts"),
    ]
    res = store.store_candidates(
        user_id="user_disabled",
        session_id="s1",
        source_message_id="m1",
        candidates=cands,
    )

    assert len(res.created) == 0
    assert len(res.skipped) == 2
    assert all(sk.reason == "memory_disabled" for sk in res.skipped)
    assert len(repo.memories) == 0


def test_duplicates_refresh_instead_of_inserting():
    """Active duplicates refresh updated_at and last_used_at instead of creating duplicates."""
    repo = FakeStoreRepository()
    recall = StubRecall()
    lifecycle = Lifecycle(repository=repo, recall=recall)
    store = MemoryStore(
        repository=repo,
        lifecycle=lifecycle,
        user_lookup=lambda uid: User(user_id=uid, display_name="Test"),
    )

    fixed_now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    cand = CandidateMemory(
        type=MemoryType.PANTRY,
        text="Olive oil in pantry",
        structured={"item": "olive oil"},
    )

    # 1. First insert
    res1 = store.store_candidates(
        user_id="u1", session_id="s1", source_message_id="m1", candidates=[cand], now=fixed_now
    )
    assert len(res1.created) == 1
    mem_id = res1.created[0].id
    assert len(res1.duplicates_skipped) == 0

    # 2. Second insert with duplicate item
    later = fixed_now + timedelta(hours=2)
    res2 = store.store_candidates(
        user_id="u1", session_id="s2", source_message_id="m2", candidates=[cand], now=later
    )
    assert len(res2.created) == 0
    assert res2.duplicates_skipped == [mem_id]
    assert repo.memories[mem_id]["updated_at"] == later
    assert repo.memories[mem_id]["last_used_at"] == later


def test_ttl_and_protection_policies():
    """Pantry & temp context get expires_at; allergies get None and are protected."""
    repo = FakeStoreRepository()
    recall = StubRecall()
    lifecycle = Lifecycle(repository=repo, recall=recall)
    store = MemoryStore(
        repository=repo,
        lifecycle=lifecycle,
        user_lookup=lambda uid: User(user_id=uid, display_name="Test"),
    )

    fixed_now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    cands = [
        CandidateMemory(type=MemoryType.PANTRY, text="Basmati rice", suggested_ttl_hours=100),
        CandidateMemory(type=MemoryType.TEMPORARY_CONTEXT, text="Dinner for 4", suggested_ttl_hours=6),
        CandidateMemory(type=MemoryType.ALLERGY, text="Peanut allergy", structured={"allergen": "peanuts"}),
        CandidateMemory(type=MemoryType.PREFERENCE, text="Loves pasta"),
    ]

    res = store.store_candidates(
        user_id="u1", session_id="s1", source_message_id="m1", candidates=cands, now=fixed_now
    )

    assert len(res.created) == 4
    pantry_mem = next(m for m in res.created if m.type == MemoryType.PANTRY)
    temp_mem = next(m for m in res.created if m.type == MemoryType.TEMPORARY_CONTEXT)
    allergy_mem = next(m for m in res.created if m.type == MemoryType.ALLERGY)
    pref_mem = next(m for m in res.created if m.type == MemoryType.PREFERENCE)

    assert pantry_mem.expires_at == fixed_now + timedelta(hours=100)
    assert temp_mem.expires_at == fixed_now + timedelta(hours=6)
    assert allergy_mem.expires_at is None
    assert allergy_mem.protected is True
    assert pref_mem.expires_at is None


def test_low_confidence_filtering():
    """Low-confidence non-allergies are skipped; low-confidence allergies are retained."""
    repo = FakeStoreRepository()
    recall = StubRecall()
    lifecycle = Lifecycle(repository=repo, recall=recall)
    store = MemoryStore(
        repository=repo,
        lifecycle=lifecycle,
        user_lookup=lambda uid: User(user_id=uid, display_name="Test"),
        min_confidence=0.5,
    )

    cands = [
        CandidateMemory(type=MemoryType.PREFERENCE, text="Might like mushrooms", confidence=0.3),
        CandidateMemory(type=MemoryType.ALLERGY, text="Might be allergic to shrimp", confidence=0.2),
    ]

    res = store.store_candidates(
        user_id="u1", session_id="s1", source_message_id="m1", candidates=cands
    )

    assert len(res.created) == 1
    assert res.created[0].type == MemoryType.ALLERGY
    assert len(res.skipped) == 1
    assert res.skipped[0].reason == "low_confidence"


def test_single_candidate_error_does_not_abort_batch():
    """A failure on one candidate does not stop other candidates from being persisted."""
    repo = FakeStoreRepository()
    recall = StubRecall()
    lifecycle = Lifecycle(repository=repo, recall=recall)
    store = MemoryStore(
        repository=repo,
        lifecycle=lifecycle,
        user_lookup=lambda uid: User(user_id=uid, display_name="Test"),
    )

    good_cand1 = CandidateMemory(type=MemoryType.PREFERENCE, text="Loves pesto")
    good_cand2 = CandidateMemory(type=MemoryType.PANTRY, text="Garlic")

    # Mock insert_memory to fail specifically on 'Loves pesto'
    original_insert = repo.insert_memory
    def flaky_insert(mem: Memory) -> str:
        if mem.text == "Loves pesto":
            raise RuntimeError("Database write error")
        return original_insert(mem)

    repo.insert_memory = flaky_insert

    res = store.store_candidates(
        user_id="u1", session_id="s1", source_message_id="m1", candidates=[good_cand1, good_cand2]
    )

    assert len(res.created) == 1
    assert res.created[0].text == "Garlic"
    assert len(res.skipped) == 1
    assert res.skipped[0].reason == "error"


def test_correction_flow_single_ambiguous_and_allergy_confirmation():
    """Verify single supersede, ambiguous retention, and allergy confirmation handling."""
    repo = FakeStoreRepository()

    # Pre-populate an existing preference and allergy
    old_pref = Memory(user_id="u1", type=MemoryType.PREFERENCE, text="Loves dark chocolate")
    pref_id = repo.insert_memory(old_pref)

    old_allergy = Memory.model_construct(
        user_id="u1",
        type=MemoryType.ALLERGY,
        text="Allergic to walnuts",
        protected=True,
        expires_at=None,
        status=MemoryStatus.ACTIVE,
    )
    allergy_id = repo.insert_memory(old_allergy)

    # 1. Single clear match for preference -> supersedes automatically
    recall_pref_single = RecallResult(
        recalled=[
            RecalledMemory(
                memory=old_pref,
                score=ScoreBreakdown(similarity=0.92, final_score=0.92),
            )
        ]
    )
    lifecycle_pref = Lifecycle(repository=repo, recall=StubRecall(recall_pref_single))
    store_pref = MemoryStore(
        repository=repo,
        lifecycle=lifecycle_pref,
        user_lookup=lambda uid: User(user_id=uid, display_name="Test"),
    )

    cand_pref_update = CandidateMemory(
        type=MemoryType.PREFERENCE,
        text="Now dislikes dark chocolate",
        is_correction_of_text="Loves dark chocolate",
    )
    res_pref = store_pref.store_candidates("u1", "s1", "m1", [cand_pref_update])
    assert len(res_pref.superseded) == 1
    assert res_pref.superseded[0].old_id == pref_id
    assert repo.memories[pref_id]["status"] == "superseded"

    # 2. Allergy correction -> requires confirmation
    recall_allergy = RecallResult(
        recalled=[
            RecalledMemory.model_construct(
                memory=old_allergy,
                score=ScoreBreakdown(similarity=0.95, final_score=0.95),
            )
        ]
    )
    lifecycle_allergy = Lifecycle(repository=repo, recall=StubRecall(recall_allergy))
    store_allergy = MemoryStore(
        repository=repo,
        lifecycle=lifecycle_allergy,
        user_lookup=lambda uid: User(user_id=uid, display_name="Test"),
    )

    cand_allergy_update = CandidateMemory(
        type=MemoryType.ALLERGY,
        text="Allergic to walnuts and cashews",
        is_correction_of_text="Allergic to walnuts",
    )
    res_allergy = store_allergy.store_candidates("u1", "s1", "m1", [cand_allergy_update])

    assert len(res_allergy.needs_confirmation) == 1
    pending = res_allergy.needs_confirmation[0]
    assert pending.target_memory.id == allergy_id
    assert repo.memories[allergy_id]["status"] == "active"  # Not changed yet

    # Confirm pending change
    confirm_res = store_allergy.confirm_pending("u1", pending)
    assert confirm_res.status == "superseded"
    assert repo.memories[allergy_id]["status"] == "superseded"
