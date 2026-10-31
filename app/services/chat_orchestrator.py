"""Chat orchestrator coordinating conversation flow, memory extraction, storage, recall, and response generation."""

from datetime import datetime
import logging
import time
from typing import Any, Callable, Optional

from app.domain.models import (
    ChatRequest,
    ChatResponse,
    Memory,
    MemoryType,
    MemoryUsed,
    Message,
    MessageRole,
    StepTiming,
    TraceInfo,
    User,
    utc_now,
)
from app.infra import config
from app.infra.memory_repository import VectorIndexNotReadyError
from app.services.memory_recall import RecallResult

logger = logging.getLogger(__name__)


def _dict_to_message(doc: dict[str, Any]) -> Message:
    """Convert a message database dictionary to a Message model."""
    doc_copy = dict(doc)
    doc_id = str(doc_copy.pop("_id", doc_copy.get("id", "")))
    doc_copy["id"] = doc_id
    raw_role = doc_copy.get("role")
    if isinstance(raw_role, str):
        try:
            doc_copy["role"] = MessageRole(raw_role)
        except ValueError:
            pass
    return Message(**doc_copy)


class ChatOrchestrator:
    """Orchestrates turn-by-turn chat processing, memory lifecycle, and generation."""

    def __init__(
        self,
        extractor: Any,
        store: Any,
        recall: Any,
        ranker_fn: Any,
        chef: Any,
        repository: Any,
        now_fn: Optional[Callable[[], datetime]] = None,
        history_turns: Optional[int] = None,
        recall_limit: Optional[int] = None,
        max_message_chars: Optional[int] = None,
    ) -> None:
        """Initialize chat orchestrator with injected collaborators and configuration."""
        self.extractor = extractor
        self.store = store
        self.recall = recall
        self.ranker_fn = ranker_fn
        self.chef = chef
        self.repository = repository
        self.now_fn = now_fn or utc_now
        self.history_turns = (
            history_turns
            if history_turns is not None
            else int(getattr(config, "HISTORY_TURNS", 6))
        )
        self.recall_limit = (
            recall_limit
            if recall_limit is not None
            else int(getattr(config, "RECALL_LIMIT", 5))
        )
        self.max_message_chars = (
            max_message_chars
            if max_message_chars is not None
            else int(getattr(config, "MAX_MESSAGE_CHARS", 2000))
        )

    def handle_message(self, request: ChatRequest) -> ChatResponse:
        """Process a user conversational turn following the complete lifecycle flow."""
        now = self.now_fn()
        timings: list[StepTiming] = []
        degraded_steps: list[str] = []
        warnings: list[str] = []

        # 1. Validate input
        raw_message = request.message or ""
        message_text = raw_message.strip()

        if not message_text:
            return ChatResponse(
                answer="Hello! How can I help with your cooking or meal planning today?",
                memories_used=[],
                memories_created=[],
                memories_superseded=[],
                safety_warnings=[],
                pending_confirmations=[],
                ambiguous_corrections=[],
                warnings=[],
                trace=TraceInfo(
                    extracted=[],
                    stored_ids=[],
                    superseded=[],
                    duplicates_refreshed=[],
                    skipped=[],
                    recalled_count=0,
                    always_applied_ids=[],
                    timings=[],
                    degraded_steps=[],
                ),
                message_id=None,
            )

        if len(message_text) > self.max_message_chars:
            return ChatResponse(
                answer=(
                    f"Your message is too long ({len(message_text)} characters). "
                    f"Please keep messages under {self.max_message_chars} characters."
                ),
                memories_used=[],
                memories_created=[],
                memories_superseded=[],
                safety_warnings=[],
                pending_confirmations=[],
                ambiguous_corrections=[],
                warnings=[f"Input message exceeded maximum length of {self.max_message_chars} characters."],
                trace=TraceInfo(
                    extracted=[],
                    stored_ids=[],
                    superseded=[],
                    duplicates_refreshed=[],
                    skipped=[],
                    recalled_count=0,
                    always_applied_ids=[],
                    timings=[],
                    degraded_steps=[],
                ),
                message_id=None,
            )

        # 2. Ensure user exists; read settings.memory_enabled
        user_doc = self.repository.get_user(request.user_id)
        if user_doc is None:
            new_user = User(user_id=request.user_id, display_name=request.user_id)
            self.repository.upsert_user(new_user)
            memory_enabled = True
        else:
            if hasattr(user_doc, "settings"):
                memory_enabled = getattr(user_doc.settings, "memory_enabled", True)
            elif isinstance(user_doc, dict):
                memory_enabled = user_doc.get("settings", {}).get("memory_enabled", True)
            else:
                memory_enabled = True

        # 3. Load recent chat history for this session
        recent_raw_msgs = self.repository.list_messages(
            user_id=request.user_id,
            session_id=request.session_id,
            limit=self.history_turns * 2,
        )
        chat_history: list[tuple[str, str]] = []
        recent_context_lines: list[str] = []
        for msg_doc in recent_raw_msgs:
            role_val = msg_doc.get("role", "user")
            content_val = msg_doc.get("content", "")
            chat_history.append((role_val, content_val))
            recent_context_lines.append(f"{role_val}: {content_val}")

        # 4. Persist the user message first
        user_msg = Message(
            user_id=request.user_id,
            session_id=request.session_id,
            role=MessageRole.USER,
            content=message_text,
            created_at=now,
        )
        try:
            user_msg_id = self.repository.insert_message(user_msg)
        except Exception as exc:
            logger.warning("Failed to persist user message: %s", exc)
            user_msg_id = user_msg.id

        # 5. EXTRACT
        candidates: list[Any] = []
        if memory_enabled and self.extractor is not None:
            t0 = time.perf_counter()
            try:
                extraction_result = self.extractor.extract(
                    user_message=message_text,
                    recent_context=recent_context_lines,
                )
                if hasattr(extraction_result, "candidates"):
                    candidates = list(extraction_result.candidates)
            except Exception as exc:
                logger.error("Error during extraction step: %s", exc)
                degraded_steps.append("extraction")
                candidates = []
            finally:
                ms = (time.perf_counter() - t0) * 1000.0
                timings.append(StepTiming(step="extraction", ms=ms))
                logger.info("Step extraction took %.2fms (found %d candidates)", ms, len(candidates))

        # 6. STORE (must happen before recall)
        created_memories: list[Memory] = []
        superseded_ids: list[str] = []
        duplicates_refreshed: list[str] = []
        pending_confirmations: list[Any] = []
        ambiguous_corrections: list[Any] = []
        skipped_items: list[dict[str, Any]] = []

        if memory_enabled and candidates and self.store is not None:
            t0 = time.perf_counter()
            try:
                store_result = self.store.store_candidates(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    source_message_id=user_msg_id,
                    candidates=candidates,
                    now=now,
                )
                created_memories = getattr(store_result, "created", [])
                superseded_objs = getattr(store_result, "superseded", [])
                for sup in superseded_objs:
                    old_id = getattr(sup, "old_id", None)
                    if old_id:
                        superseded_ids.append(str(old_id))
                    elif isinstance(sup, str):
                        superseded_ids.append(sup)
                duplicates_refreshed = getattr(store_result, "duplicates_skipped", [])
                pending_confirmations = getattr(store_result, "needs_confirmation", [])
                ambiguous_corrections = getattr(store_result, "ambiguous_corrections", [])
                raw_skipped = getattr(store_result, "skipped", [])
                for sk in raw_skipped:
                    if isinstance(sk, dict):
                        skipped_items.append(sk)
                    else:
                        skipped_items.append({
                            "reason": getattr(sk, "reason", "unknown"),
                            "summary": getattr(sk, "summary", str(sk)),
                        })
            except Exception as exc:
                logger.error("Error during store step: %s", exc)
                degraded_steps.append("store")
            finally:
                ms = (time.perf_counter() - t0) * 1000.0
                timings.append(StepTiming(step="store", ms=ms))
                logger.info(
                    "Step store took %.2fms (created=%d, superseded=%d)",
                    ms,
                    len(created_memories),
                    len(superseded_ids),
                )

        # 7. RECALL
        recalled: list[Any] = []
        always_applied: list[Memory] = []
        recall_result_obj: Optional[RecallResult] = None

        if memory_enabled and self.recall is not None:
            t0 = time.perf_counter()
            try:
                recall_result_obj = self.recall.recall(
                    user_id=request.user_id,
                    query_text=message_text,
                    limit=self.recall_limit,
                )
                recalled = getattr(recall_result_obj, "recalled", [])
                always_applied = getattr(recall_result_obj, "always_applied", [])
                warning = getattr(recall_result_obj, "warning", None)
                if warning:
                    warnings.append(warning)
                    degraded_steps.append("recall")
            except (VectorIndexNotReadyError, Exception) as exc:
                logger.error("Error during recall step: %s", exc)
                degraded_steps.append("recall")
                warnings.append("Memory search is unavailable right now, answering without it.")
                recalled = []
                always_applied = []
            finally:
                ms = (time.perf_counter() - t0) * 1000.0
                timings.append(StepTiming(step="recall", ms=ms))
                logger.info(
                    "Step recall took %.2fms (recalled=%d, always_applied=%d)",
                    ms,
                    len(recalled),
                    len(always_applied),
                )

        # 8. GENERATE
        answer = ""
        validated_used_ids: list[str] = []
        safety_warnings: list[str] = []
        generation_success = False

        if self.chef is not None:
            t0 = time.perf_counter()
            try:
                chef_result = self.chef.generate(
                    user_message=message_text,
                    recalled=recalled,
                    always_applied=always_applied,
                    chat_history=chat_history,
                )
                answer = getattr(chef_result, "answer", "")
                validated_used_ids = getattr(chef_result, "memory_ids_used", [])
                raw_findings = getattr(chef_result, "safety_findings", [])
                for finding in raw_findings:
                    if hasattr(finding, "allergen"):
                        term = getattr(finding, "matched_term", "")
                        safety_warnings.append(f"Allergen conflict detected: {finding.allergen} ('{term}')")
                    else:
                        safety_warnings.append(str(finding))
                generation_success = True
            except Exception as exc:
                logger.error("Error during chef generation step: %s", exc)
                degraded_steps.append("generate")
                answer = (
                    "I apologize, but I encountered a temporary problem while generating "
                    "your culinary suggestions. Please try asking your question again in a moment."
                )
                validated_used_ids = []
            finally:
                ms = (time.perf_counter() - t0) * 1000.0
                timings.append(StepTiming(step="generate", ms=ms))
                logger.info(
                    "Step generate took %.2fms (success=%s, used_ids=%d)",
                    ms,
                    generation_success,
                    len(validated_used_ids),
                )

        # 9. After successful reply only: mark memories used
        if generation_success and validated_used_ids and self.recall is not None:
            try:
                used_recalled = [rm for rm in recalled if rm.memory.id in validated_used_ids]
                used_always = [m for m in always_applied if m.id in validated_used_ids]
                pruned_result = RecallResult(recalled=used_recalled, always_applied=used_always)
                self.recall.mark_recalled(pruned_result)
            except Exception as exc:
                logger.warning("Failed to mark recalled memories: %s", exc)

        # 10. Build memories_used
        memories_used: list[MemoryUsed] = []
        recalled_map = {rm.memory.id: rm for rm in recalled if hasattr(rm, "memory")}
        always_map = {m.id: m for m in always_applied if hasattr(m, "id")}

        for uid in validated_used_ids:
            if uid in recalled_map:
                rm = recalled_map[uid]
                memories_used.append(
                    MemoryUsed(
                        memory_id=rm.memory.id,
                        text=rm.memory.text,
                        type=rm.memory.type,
                        score=float(rm.score.final_score),
                        reasons=list(rm.reasons),
                    )
                )
            elif uid in always_map:
                m = always_map[uid]
                memories_used.append(
                    MemoryUsed(
                        memory_id=m.id,
                        text=m.text,
                        type=m.type,
                        score=1.0,
                        reasons=["always-applied constraint"],
                    )
                )

        # 11. Persist assistant message
        created_ids = [m.id for m in created_memories if hasattr(m, "id")]
        asst_msg = Message(
            user_id=request.user_id,
            session_id=request.session_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            memories_used=memories_used,
            memories_created=created_ids,
            created_at=self.now_fn(),
        )
        try:
            asst_msg_id = self.repository.insert_message(asst_msg)
        except Exception as exc:
            logger.warning("Failed to persist assistant message: %s", exc)
            asst_msg_id = asst_msg.id

        # 12. Build and return ChatResponse
        trace = TraceInfo(
            extracted=candidates,
            stored_ids=created_ids,
            superseded=superseded_ids,
            duplicates_refreshed=duplicates_refreshed,
            skipped=skipped_items,
            recalled_count=len(recalled),
            always_applied_ids=[m.id for m in always_applied if hasattr(m, "id")],
            timings=timings,
            degraded_steps=degraded_steps,
        )

        return ChatResponse(
            answer=answer,
            memories_used=memories_used,
            memories_created=created_memories,
            memories_superseded=superseded_ids,
            safety_warnings=safety_warnings,
            pending_confirmations=pending_confirmations,
            ambiguous_corrections=ambiguous_corrections,
            warnings=warnings,
            trace=trace,
            message_id=asst_msg_id,
        )

    def confirm_change(self, user_id: str, pending: Any) -> Any:
        """Pass-through to store.confirm_pending when user clicks confirm on a pending change."""
        if self.store is None or not hasattr(self.store, "confirm_pending"):
            raise RuntimeError("MemoryStore is not configured for pending change confirmation.")
        return self.store.confirm_pending(user_id=user_id, pending=pending)

    def get_history(
        self,
        user_id: str,
        session_id: str,
        limit: int = 50,
    ) -> list[Message]:
        """Retrieve conversational message history for a user session."""
        docs = self.repository.list_messages(user_id=user_id, session_id=session_id, limit=limit)
        return [_dict_to_message(d) for d in docs]

    def list_sessions(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List active user sessions with metadata."""
        return self.repository.list_sessions(user_id=user_id, limit=limit)
