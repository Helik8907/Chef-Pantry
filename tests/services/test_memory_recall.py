"""Offline unit tests for memory recall service and vector search pipeline builder."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.domain.models import (
    Memory,
    MemoryStatus,
    MemoryType,
    User,
    UserSettings,
    utc_now,
)
from app.infra.memory_repository import (
    VectorIndexNotReadyError,
    build_vector_search_pipeline,
)
from app.infra.providers.mock_embedding import MockEmbeddingStrategy
from app.services.memory_recall import MemoryRecall, RecallResult


class FakeMemoryRepository:
    """In-memory test double for MemoryRepository."""

    def __init__(
        self,
        vector_results: Optional[list[dict[str, Any]]] = None,
        allergies: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self.vector_results: list[dict[str, Any]] = vector_results or []
        self.allergies: list[dict[str, Any]] = allergies or []
        self.marked_used_ids: list[str] = []
        self.raise_not_ready: bool = False

    def vector_search(
        self,
        query_text: str,
        user_id: str,
        limit: int = 10,
        memory_types: Optional[list[str]] = None,
        statuses: tuple[str, ...] = ("active",),
        num_candidates: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        if self.raise_not_ready:
            raise VectorIndexNotReadyError("Vector search index 'memories_vector_index' is not ready.")
        return self.vector_results

    def get_active_by_type(
        self,
        user_id: str,
        memory_type: Any,
    ) -> list[dict[str, Any]]:
        type_str = memory_type.value if hasattr(memory_type, "value") else str(memory_type)
        if type_str == "allergy":
            return self.allergies
        return []

    def mark_used(self, memory_ids: list[str]) -> int:
        self.marked_used_ids.extend(memory_ids)
        return len(memory_ids)


def test_build_vector_search_pipeline_structure():
    """Verify aggregation pipeline construction, pre-filters, over-fetch, and projection."""
    strategy = MockEmbeddingStrategy(dimensions=64, num_candidates=100)
    fixed_now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)

    pipeline = build_vector_search_pipeline(
        strategy=strategy,
        query_text="pasta night",
        user_id="user_123",
        limit=5,
        memory_types=["preference"],
        statuses=("active",),
        now=fixed_now,
    )

    assert len(pipeline) == 4

    # 1. $vectorSearch stage
    vs_stage = pipeline[0]["$vectorSearch"]
    assert vs_stage["limit"] == 15  # 5 * 3 overfetch
    assert vs_stage["numCandidates"] == 100
    assert vs_stage["filter"]["user_id"] == "user_123"
    assert vs_stage["filter"]["status"] == "active"
    assert vs_stage["filter"]["type"] == "preference"

    # 2. $match stage for expiration
    match_stage = pipeline[1]["$match"]
    or_clauses = match_stage["$or"]
    assert {"expires_at": None} in or_clauses
    assert {"expires_at": {"$exists": False}} in or_clauses
    assert {"expires_at": {"$gt": fixed_now}} in or_clauses

    # 3. $project stage excluding embedding and exposing _score
    project_stage = pipeline[2]["$project"]
    assert project_stage["embedding"] == 0
    assert project_stage["_score"] == {"$meta": "vectorSearchScore"}

    # 4. Trimming $limit stage
    limit_stage = pipeline[3]["$limit"]
    assert limit_stage == 5


def test_build_vector_search_pipeline_overfetch_capping():
    """Verify that over-fetch limit is capped by num_candidates."""
    strategy = MockEmbeddingStrategy(dimensions=64, num_candidates=20)
    pipeline = build_vector_search_pipeline(
        strategy=strategy,
        query_text="desserts",
        user_id="user_123",
        limit=10,
        num_candidates=20,
    )
    # 10 * 3 = 30, capped by num_candidates=20
    assert pipeline[0]["$vectorSearch"]["limit"] == 20


def test_allergies_always_included_and_deduplicated():
    """Active allergies are always in always_applied and de-duplicated from recalled."""
    allergy_doc = {
        "_id": "012345678901234567890001",
        "user_id": "user_chef",
        "type": "allergy",
        "text": "Severe peanut allergy",
        "status": "active",
        "protected": True,
        "expires_at": None,
        "_score": 0.95,
    }
    pref_doc = {
        "_id": "012345678901234567890002",
        "user_id": "user_chef",
        "type": "preference",
        "text": "Loves Italian herbs",
        "status": "active",
        "_score": 0.88,
    }

    # Repository returns allergy in get_active_by_type, and both in vector_search
    repo = FakeMemoryRepository(
        vector_results=[allergy_doc, pref_doc],
        allergies=[allergy_doc],
    )
    service = MemoryRecall(repository=repo)

    result = service.recall(user_id="user_chef", query_text="What herbs pair with chicken?")

    assert len(result.always_applied) == 1
    assert result.always_applied[0].id == "012345678901234567890001"
    assert result.always_applied[0].type == MemoryType.ALLERGY

    # Recalled must contain only pref_doc (allergy was de-duplicated)
    assert len(result.recalled) == 1
    assert result.recalled[0].memory.id == "012345678901234567890002"
    assert result.recalled[0].score.similarity == 0.88
    assert "semantic match (0.88)" in result.recalled[0].reasons


def test_lifecycle_exclusions():
    """Deleted, superseded, and expired memories are excluded from recall results."""
    now = utc_now()
    past_expiry = now - timedelta(hours=2)

    valid_active = {
        "_id": "012345678901234567890010",
        "user_id": "user_1",
        "type": "preference",
        "text": "Likes quick 30-minute meals",
        "status": "active",
        "_score": 0.90,
    }
    deleted_mem = {
        "_id": "012345678901234567890011",
        "user_id": "user_1",
        "type": "preference",
        "text": "Old preference",
        "status": "deleted",
        "_score": 0.85,
    }
    superseded_mem = {
        "_id": "012345678901234567890012",
        "user_id": "user_1",
        "type": "preference",
        "text": "Superseded item",
        "status": "superseded",
        "superseded_by": "012345678901234567890010",
        "_score": 0.80,
    }
    expired_mem = {
        "_id": "012345678901234567890013",
        "user_id": "user_1",
        "type": "temporary_context",
        "text": "Cooking for dinner guests tonight",
        "status": "active",
        "expires_at": past_expiry,
        "_score": 0.95,
    }

    repo = FakeMemoryRepository(
        vector_results=[valid_active, deleted_mem, superseded_mem, expired_mem],
        allergies=[],
    )
    service = MemoryRecall(repository=repo)
    result = service.recall(user_id="user_1", query_text="meal idea")

    assert len(result.recalled) == 1
    assert result.recalled[0].memory.id == "012345678901234567890010"


def test_memory_enabled_false_short_circuits():
    """When user settings disable memory retention, recall returns empty result immediately."""
    user = User(
        user_id="user_opt_out",
        display_name="Opt Out User",
        settings=UserSettings(memory_enabled=False),
    )
    repo = FakeMemoryRepository(
        vector_results=[{
            "_id": "012345678901234567890020",
            "user_id": "user_opt_out",
            "type": "preference",
            "text": "Vegan",
            "status": "active",
            "_score": 0.99,
        }],
        allergies=[{
            "_id": "012345678901234567890021",
            "user_id": "user_opt_out",
            "type": "allergy",
            "text": "Peanuts",
            "status": "active",
        }],
    )

    service = MemoryRecall(
        repository=repo,
        user_lookup=lambda uid: user if uid == "user_opt_out" else None,
    )
    result = service.recall(user_id="user_opt_out", query_text="dinner")

    assert len(result.recalled) == 0
    assert len(result.always_applied) == 0
    assert result.matched_filters.get("memory_enabled") is False


def test_custom_rerank_callable():
    """Custom rerank callable modifies the ordering of candidate memories."""
    doc_a = {
        "_id": "012345678901234567890031",
        "user_id": "user_1",
        "type": "preference",
        "text": "Apples",
        "status": "active",
        "_score": 0.90,
    }
    doc_b = {
        "_id": "012345678901234567890032",
        "user_id": "user_1",
        "type": "preference",
        "text": "Bananas",
        "status": "active",
        "_score": 0.70,
    }

    repo = FakeMemoryRepository(vector_results=[doc_a, doc_b])

    # Reverse sort reranker (lowest similarity first)
    custom_reranker = lambda items: sorted(items, key=lambda rm: rm.score.similarity)
    service = MemoryRecall(repository=repo, rerank=custom_reranker)

    result = service.recall(user_id="user_1", query_text="fruits", limit=2)
    assert len(result.recalled) == 2
    assert result.recalled[0].memory.text == "Bananas"
    assert result.recalled[1].memory.text == "Apples"


def test_vector_index_not_ready_error_handling():
    """VectorIndexNotReadyError yields an empty result with a warning without crashing."""
    allergy_doc = {
        "_id": "012345678901234567890040",
        "user_id": "user_1",
        "type": "allergy",
        "text": "Shellfish allergy",
        "status": "active",
    }
    repo = FakeMemoryRepository(allergies=[allergy_doc])
    repo.raise_not_ready = True

    service = MemoryRecall(repository=repo)
    result = service.recall(user_id="user_1", query_text="seafood")

    assert len(result.recalled) == 0
    assert len(result.always_applied) == 1
    assert result.warning is not None
    assert "not ready" in result.warning


def test_mark_recalled():
    """mark_recalled invokes mark_used with both recalled and always-applied memory IDs."""
    allergy_doc = {
        "_id": "012345678901234567890050",
        "user_id": "user_1",
        "type": "allergy",
        "text": "Gluten allergy",
        "status": "active",
    }
    pref_doc = {
        "_id": "012345678901234567890051",
        "user_id": "user_1",
        "type": "preference",
        "text": "Prefers sourdough",
        "status": "active",
        "_score": 0.85,
    }

    repo = FakeMemoryRepository(vector_results=[pref_doc], allergies=[allergy_doc])
    service = MemoryRecall(repository=repo)

    result = service.recall(user_id="user_1", query_text="bread")
    service.mark_recalled(result)

    assert set(repo.marked_used_ids) == {
        "012345678901234567890050",
        "012345678901234567890051",
    }
