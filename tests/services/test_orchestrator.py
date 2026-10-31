"""Offline unit tests for chat orchestrator and container composition root."""

from datetime import datetime, timezone
from typing import Any, Optional
import pytest
from pydantic import BaseModel

from app.domain.models import (
    CandidateMemory,
    ChatRequest,
    ChatResponse,
    Memory,
    MemoryStatus,
    MemoryType,
    Message,
    MessageRole,
    RecalledMemory,
    ScoreBreakdown,
    User,
    UserSettings,
    utc_now,
)
from app.domain.safety import SafetyFinding
from app.infra.memory_repository import VectorIndexNotReadyError
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.chef import ChefResult
from app.services.container import build_container, health_check
from app.services.extraction import ExtractionResult
from app.services.memory_recall import RecallResult


# ============================================================================
# FAKE TEST DOUBLES
# ============================================================================

class FakeRepository:
    """In-memory test double for MemoryRepository."""

    def __init__(self, users: Optional[dict[str, Any]] = None) -> None:
        self.users: dict[str, dict[str, Any]] = users or {}
        self.messages: list[dict[str, Any]] = []
        self.marked_used_ids: list[str] = []
        self.vector_status: str = "ready"
        self.raise_on_insert: bool = False

    def insert_message(self, message: Any) -> str:
        if self.raise_on_insert:
            raise RuntimeError("Database connection lost during insert_message.")
        doc = message.model_dump(by_alias=True) if hasattr(message, "model_dump") else dict(message)
        mid = doc.get("_id") or doc.get("id") or f"msg_{len(self.messages) + 1}"
        doc["_id"] = str(mid)
        self.messages.append(doc)
        return str(mid)

    def list_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        matching = [
            m for m in self.messages
            if m.get("user_id") == user_id and m.get("session_id") == session_id
        ]
        return matching[-limit:]

    def list_sessions(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        sessions_map: dict[str, list[dict[str, Any]]] = {}
        for m in self.messages:
            if m.get("user_id") == user_id:
                sessions_map.setdefault(m["session_id"], []).append(m)

        result: list[dict[str, Any]] = []
        for sid, msgs in sessions_map.items():
            times = [m["created_at"] for m in msgs]
            result.append({
                "session_id": sid,
                "first_message_time": min(times),
                "last_message_time": max(times),
                "message_count": len(msgs),
            })
        return result[:limit]

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        return self.users.get(user_id)

    def upsert_user(self, user: Any) -> dict[str, Any]:
        doc = user.model_dump(by_alias=True) if hasattr(user, "model_dump") else dict(user)
        uid = doc["user_id"]
        self.users[uid] = doc
        return doc

    def mark_used(self, memory_ids: list[str]) -> int:
        self.marked_used_ids.extend(memory_ids)
        return len(memory_ids)

    def vector_index_status(self) -> str:
        return self.vector_status


class FakeStoreResult:
    """Mock result from store_candidates."""

    def __init__(
        self,
        created: Optional[list[Any]] = None,
        superseded: Optional[list[Any]] = None,
        duplicates_skipped: Optional[list[str]] = None,
        needs_confirmation: Optional[list[Any]] = None,
        ambiguous_corrections: Optional[list[Any]] = None,
        skipped: Optional[list[Any]] = None,
    ) -> None:
        self.created = created or []
        self.superseded = superseded or []
        self.duplicates_skipped = duplicates_skipped or []
        self.needs_confirmation = needs_confirmation or []
        self.ambiguous_corrections = ambiguous_corrections or []
        self.skipped = skipped or []


class FakeSupersedeItem:
    def __init__(self, old_id: str, new_id: str) -> None:
        self.old_id = old_id
        self.new_id = new_id


class FakeExtractor:
    def __init__(self, candidates: Optional[list[CandidateMemory]] = None) -> None:
        self.candidates = candidates or []
        self.raise_exc: Optional[Exception] = None
        self.calls: list[dict[str, Any]] = []

    def extract(self, user_message: str, recent_context: Optional[list[str]] = None) -> ExtractionResult:
        self.calls.append({"user_message": user_message, "recent_context": recent_context})
        if self.raise_exc:
            raise self.raise_exc
        return ExtractionResult(candidates=self.candidates)


class FakeStore:
    def __init__(self, result: Optional[FakeStoreResult] = None) -> None:
        self.result = result or FakeStoreResult()
        self.raise_exc: Optional[Exception] = None
        self.calls: list[dict[str, Any]] = []

    def store_candidates(
        self,
        user_id: str,
        session_id: str,
        source_message_id: str,
        candidates: list[Any],
        now: Optional[datetime] = None,
    ) -> FakeStoreResult:
        self.calls.append({
            "user_id": user_id,
            "session_id": session_id,
            "source_message_id": source_message_id,
            "candidates": candidates,
        })
        if self.raise_exc:
            raise self.raise_exc
        return self.result

    def confirm_pending(self, user_id: str, pending: Any) -> Any:
        return {"status": "confirmed", "user_id": user_id, "pending": pending}


class FakeRecall:
    def __init__(self, result: Optional[RecallResult] = None) -> None:
        self.result = result or RecallResult()
        self.raise_exc: Optional[Exception] = None
        self.calls: list[dict[str, Any]] = []
        self.marked_recalled_results: list[RecallResult] = []

    def recall(
        self,
        user_id: str,
        query_text: str,
        limit: int = 5,
        memory_types: Optional[list[str]] = None,
    ) -> RecallResult:
        self.calls.append({"user_id": user_id, "query_text": query_text, "limit": limit})
        if self.raise_exc:
            raise self.raise_exc
        return self.result

    def mark_recalled(self, result: RecallResult) -> None:
        self.marked_recalled_results.append(result)


class FakeChef:
    def __init__(self, result: Optional[ChefResult] = None) -> None:
        self.result = result or ChefResult(answer="Chef advice", memory_ids_used=[])
        self.raise_exc: Optional[Exception] = None
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        user_message: str,
        recalled: list[RecalledMemory],
        always_applied: list[Memory],
        chat_history: Optional[list[tuple[str, str]]] = None,
    ) -> ChefResult:
        self.calls.append({
            "user_message": user_message,
            "recalled": recalled,
            "always_applied": always_applied,
            "chat_history": chat_history,
        })
        if self.raise_exc:
            raise self.raise_exc
        return self.result


# ============================================================================
# TESTS
# ============================================================================

def test_happy_path_orchestration():
    """Verify complete conversational turn with extraction, store, recall, generation, and trace."""
    fixed_now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    now_fn = lambda: fixed_now

    candidate = CandidateMemory(
        type=MemoryType.PREFERENCE,
        text="Likes Italian basil and garlic",
        confidence=0.9,
    )
    extractor = FakeExtractor(candidates=[candidate])

    stored_mem = Memory.model_construct(
        id="mem_pref_1",
        user_id="user_alice",
        type=MemoryType.PREFERENCE,
        text="Likes Italian basil and garlic",
    )
    store = FakeStore(result=FakeStoreResult(created=[stored_mem]))

    recalled_mem = RecalledMemory.model_construct(
        memory=stored_mem,
        score=ScoreBreakdown(similarity=0.88, final_score=0.88),
        reasons=["semantic match (0.88)"],
    )
    recall = FakeRecall(result=RecallResult(recalled=[recalled_mem], always_applied=[]))

    chef = FakeChef(result=ChefResult(
        answer="Here is a classic pesto pasta recipe. Because I remembered: Likes Italian basil and garlic.",
        memory_ids_used=["mem_pref_1"],
    ))

    repo = FakeRepository()

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=lambda x: x,
        chef=chef,
        repository=repo,
        now_fn=now_fn,
    )

    request = ChatRequest(user_id="user_alice", session_id="sess_1", message="What can I cook tonight?")
    response = orchestrator.handle_message(request)

    assert "pesto pasta" in response.answer
    assert len(response.memories_created) == 1
    assert response.memories_created[0].id == "mem_pref_1"
    assert len(response.memories_used) == 1
    assert response.memories_used[0].memory_id == "mem_pref_1"
    assert response.memories_used[0].score == 0.88
    assert response.message_id is not None

    # Trace assertions
    assert response.trace is not None
    assert len(response.trace.extracted) == 1
    assert response.trace.stored_ids == ["mem_pref_1"]
    assert response.trace.recalled_count == 1
    assert len(response.trace.timings) == 4
    timing_steps = [t.step for t in response.trace.timings]
    assert timing_steps == ["extraction", "store", "recall", "generate"]
    assert response.trace.degraded_steps == []

    # Recall mark_recalled called with validated ID
    assert len(recall.marked_recalled_results) == 1
    assert recall.marked_recalled_results[0].recalled[0].memory.id == "mem_pref_1"


def test_ordering_store_before_recall():
    """Verify that store is called BEFORE recall and superseded memory is absent from recall."""
    call_order: list[str] = []

    class OrderTrackingStore(FakeStore):
        def store_candidates(self, *args, **kwargs):
            call_order.append("store")
            return super().store_candidates(*args, **kwargs)

    class OrderTrackingRecall(FakeRecall):
        def recall(self, *args, **kwargs):
            call_order.append("recall")
            return super().recall(*args, **kwargs)

    cand = CandidateMemory(
        type=MemoryType.PREFERENCE,
        text="No longer likes cilantro",
        is_correction_of_text="Likes cilantro",
    )
    extractor = FakeExtractor(candidates=[cand])
    store = OrderTrackingStore(result=FakeStoreResult(superseded=[FakeSupersedeItem("old_cilantro", "new_cilantro")]))
    recall = OrderTrackingRecall(result=RecallResult(recalled=[], always_applied=[]))
    chef = FakeChef(result=ChefResult(answer="Understood, no cilantro.", memory_ids_used=[]))
    repo = FakeRepository()

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=lambda x: x,
        chef=chef,
        repository=repo,
    )

    request = ChatRequest(user_id="user_bob", session_id="s1", message="Actually I hate cilantro now.")
    response = orchestrator.handle_message(request)

    assert call_order == ["store", "recall"]
    assert response.memories_superseded == ["old_cilantro"]
    assert response.trace.superseded == ["old_cilantro"]


def test_memory_enabled_false():
    """When memory is disabled in user settings, extraction, store, and recall must be skipped."""
    extractor = FakeExtractor(candidates=[CandidateMemory(type=MemoryType.PREFERENCE, text="Test")])
    store = FakeStore()
    recall = FakeRecall()
    chef = FakeChef(result=ChefResult(answer="Here is a general recipe.", memory_ids_used=[]))

    user_with_disabled_memory = {
        "user_id": "user_no_mem",
        "display_name": "No Memory User",
        "settings": {"memory_enabled": False},
    }
    repo = FakeRepository(users={"user_no_mem": user_with_disabled_memory})

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=lambda x: x,
        chef=chef,
        repository=repo,
    )

    request = ChatRequest(user_id="user_no_mem", session_id="s1", message="Recipe ideas please")
    response = orchestrator.handle_message(request)

    assert response.answer == "Here is a general recipe."
    assert len(extractor.calls) == 0
    assert len(store.calls) == 0
    assert len(recall.calls) == 0
    assert response.trace.stored_ids == []
    assert response.trace.recalled_count == 0


def test_failure_isolation_extractor():
    """Extractor failure must not crash chat turn and must be flagged in degraded_steps."""
    extractor = FakeExtractor()
    extractor.raise_exc = RuntimeError("LLM rate limit on extraction")
    store = FakeStore()
    recall = FakeRecall()
    chef = FakeChef(result=ChefResult(answer="Safe chef response.", memory_ids_used=[]))
    repo = FakeRepository()

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=lambda x: x,
        chef=chef,
        repository=repo,
    )

    response = orchestrator.handle_message(ChatRequest(user_id="u1", session_id="s1", message="Hello"))
    assert response.answer == "Safe chef response."
    assert "extraction" in response.trace.degraded_steps


def test_failure_isolation_store():
    """Store failure must be caught and recorded in degraded_steps while generation proceeds."""
    candidate = CandidateMemory(type=MemoryType.PREFERENCE, text="Loves mushrooms")
    extractor = FakeExtractor(candidates=[candidate])
    store = FakeStore()
    store.raise_exc = RuntimeError("Database write failure")
    recall = FakeRecall()
    chef = FakeChef(result=ChefResult(answer="Mushroom risotto advice.", memory_ids_used=[]))
    repo = FakeRepository()

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=lambda x: x,
        chef=chef,
        repository=repo,
    )

    response = orchestrator.handle_message(ChatRequest(user_id="u1", session_id="s1", message="I love mushrooms"))
    assert response.answer == "Mushroom risotto advice."
    assert "store" in response.trace.degraded_steps


def test_failure_isolation_recall_and_index_not_ready():
    """VectorIndexNotReadyError in recall must record degraded_steps and surface warning."""
    extractor = FakeExtractor()
    store = FakeStore()
    recall = FakeRecall()
    recall.raise_exc = VectorIndexNotReadyError("Vector search index is not ready.")
    chef = FakeChef(result=ChefResult(answer="Generated without memory.", memory_ids_used=[]))
    repo = FakeRepository()

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=lambda x: x,
        chef=chef,
        repository=repo,
    )

    response = orchestrator.handle_message(ChatRequest(user_id="u1", session_id="s1", message="Help cook"))
    assert response.answer == "Generated without memory."
    assert "recall" in response.trace.degraded_steps
    assert any("Memory search is unavailable right now" in w for w in response.warnings)


def test_failure_isolation_chef_fallback():
    """Chef failure must return a friendly fallback answer and never raise an exception."""
    extractor = FakeExtractor()
    store = FakeStore()
    recall = FakeRecall()
    chef = FakeChef()
    chef.raise_exc = RuntimeError("LLM output error during chef generation")
    repo = FakeRepository()

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=lambda x: x,
        chef=chef,
        repository=repo,
    )

    response = orchestrator.handle_message(ChatRequest(user_id="u1", session_id="s1", message="Help cook"))
    assert "I apologize" in response.answer
    assert "generate" in response.trace.degraded_steps


def test_empty_and_overlength_messages():
    """Empty and over-length messages return friendly prompts without collaborator calls."""
    extractor = FakeExtractor()
    store = FakeStore()
    recall = FakeRecall()
    chef = FakeChef()
    repo = FakeRepository()

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=lambda x: x,
        chef=chef,
        repository=repo,
        max_message_chars=50,
    )

    # Empty message
    empty_resp = orchestrator.handle_message(ChatRequest(user_id="u1", session_id="s1", message="   \n  "))
    assert "How can I help" in empty_resp.answer
    assert len(extractor.calls) == 0

    # Overlength message
    long_msg = "A" * 60
    long_resp = orchestrator.handle_message(ChatRequest(user_id="u1", session_id="s1", message=long_msg))
    assert "too long" in long_resp.answer
    assert len(extractor.calls) == 0


def test_pending_confirmations_and_ambiguous_corrections():
    """Pending confirmations and ambiguous corrections from store must propagate to ChatResponse."""
    cand = CandidateMemory(type=MemoryType.ALLERGY, text="Allergic to shellfish")
    extractor = FakeExtractor(candidates=[cand])

    pending_obj = {"candidate": cand, "question": "Are you sure you want to change allergy?"}
    ambiguous_obj = {"candidate": cand, "alternatives": []}
    store = FakeStore(result=FakeStoreResult(
        needs_confirmation=[pending_obj],
        ambiguous_corrections=[ambiguous_obj],
    ))
    recall = FakeRecall()
    chef = FakeChef(result=ChefResult(answer="Understood.", memory_ids_used=[]))
    repo = FakeRepository()

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=lambda x: x,
        chef=chef,
        repository=repo,
    )

    response = orchestrator.handle_message(ChatRequest(user_id="u1", session_id="s1", message="Update allergy"))
    assert len(response.pending_confirmations) == 1
    assert len(response.ambiguous_corrections) == 1


def test_safety_findings_propagation():
    """Safety findings from chef must appear in safety_warnings."""
    extractor = FakeExtractor()
    store = FakeStore()
    recall = FakeRecall()
    finding = SafetyFinding(allergen="peanut", matched_term="peanut butter", reason="Contains peanut allergen")
    chef = FakeChef(result=ChefResult(
        answer="Be cautious with ingredients.",
        memory_ids_used=[],
        safety_findings=[finding],
    ))
    repo = FakeRepository()

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=lambda x: x,
        chef=chef,
        repository=repo,
    )

    response = orchestrator.handle_message(ChatRequest(user_id="u1", session_id="s1", message="Peanut dish recipe"))
    assert len(response.safety_warnings) == 1
    assert "peanut" in response.safety_warnings[0]


def test_container_composition_and_health_check():
    """build_container with mock modes and a fake db wires every attribute cleanly."""
    class FakeDb:
        def __init__(self):
            self.command_called = False

        def command(self, cmd):
            self.command_called = True
            return {"ok": 1.0}

    mock_settings = {
        "EMBEDDING_MODE": "mock",
        "LLM_PROVIDER": "mock",
        "EMBEDDING_DIMENSIONS": 64,
        "HISTORY_TURNS": 4,
        "RECALL_LIMIT": 3,
        "MAX_MESSAGE_CHARS": 1000,
    }
    fake_db = FakeDb()

    container = build_container(settings=mock_settings, db=fake_db)

    assert container.settings == mock_settings
    assert container.db is fake_db
    assert container.repository is not None
    assert container.vector_strategy is not None
    assert container.llm_provider is not None
    assert container.extractor is not None
    assert container.chef is not None
    assert container.recall is not None
    assert container.orchestrator is not None

    health = health_check(container)
    assert health["database_reachable"] is True
    assert health["embedding_mode"] == "mock"
    assert health["llm_provider"] == "mock"
    assert health["demo_mode"] is True
    assert "vector_index_status" in health
