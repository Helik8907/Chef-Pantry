"""Core culinary memory repository for MongoDB persistence and Atlas vector search."""

from datetime import datetime
import logging
from typing import Any, Optional
import pymongo
from pymongo.database import Database

from app.domain.models import Memory, MemoryStatus, MemoryType, utc_now
from app.infra.providers.base import VectorStrategy, markdown_to_plain_text, run_with_backoff
from app.infra.repositories.base import (
    RateLimitError,
    VectorIndexNotReadyError,
    build_vector_search_pipeline,
    ensure_utc_datetimes,
    is_rate_limit_error,
)

logger = logging.getLogger(__name__)


def _clean_doc(doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Clean MongoDB document ID to string and ensure timestamps are timezone-aware UTC."""
    if doc is not None:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        ensure_utc_datetimes(doc)
    return doc


class MemoryRepository:
    """Repository handling MongoDB persistence, indexing, and vector search for memories."""

    def __init__(self, db: Database, strategy: VectorStrategy) -> None:
        """Initialize repository with injected database and vector strategy."""
        self.db = db
        self.strategy = strategy

    def insert_memory(self, memory: Memory) -> str:
        """Persist a new memory document using vector strategy preparation."""
        doc = memory.model_dump(by_alias=True)
        doc["text"] = markdown_to_plain_text(doc.get("text", ""))
        prepared = self.strategy.prepare_document(doc)
        res = self.db.memories.insert_one(prepared)
        return str(res.inserted_id or prepared.get("_id"))

    def get_memory(self, memory_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a memory document by ID."""
        doc = self.db.memories.find_one({"_id": memory_id})
        return _clean_doc(doc)

    def list_memories(
        self,
        user_id: str,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List memories matching user ID and optional filter criteria."""
        query: dict[str, Any] = {"user_id": user_id}
        if filters:
            query.update(filters)
        cursor = self.db.memories.find(query).limit(limit)
        return [_clean_doc(doc) for doc in cursor if doc]

    def update_status(
        self,
        memory_id: str,
        status: MemoryStatus | str,
        superseded_by: Optional[str] = None,
    ) -> bool:
        """Update lifecycle status and metadata for a memory."""
        status_val = status.value if hasattr(status, "value") else str(status)
        update_fields: dict[str, Any] = {
            "status": status_val,
            "updated_at": utc_now(),
        }
        if superseded_by:
            update_fields["superseded_by"] = superseded_by
        if status_val == "deleted":
            update_fields["deleted_at"] = utc_now()

        res = self.db.memories.update_one({"_id": memory_id}, {"$set": update_fields})
        return res.matched_count > 0

    def mark_used(self, memory_ids: list[str]) -> int:
        """Increment usage count and update last_used_at timestamp for specified memories."""
        if not memory_ids:
            return 0
        res = self.db.memories.update_many(
            {"_id": {"$in": memory_ids}},
            {
                "$inc": {"use_count": 1},
                "$set": {"last_used_at": utc_now()},
            },
        )
        return res.modified_count

    def delete_memory(self, memory_id: str) -> bool:
        """Permanently delete a memory record by ID."""
        res = self.db.memories.delete_one({"_id": memory_id})
        return res.deleted_count > 0

    def get_active_by_type(
        self,
        user_id: str,
        memory_type: MemoryType | str,
    ) -> list[dict[str, Any]]:
        """Query active and non-expired memories by type for a user."""
        now = utc_now()
        type_val = memory_type.value if hasattr(memory_type, "value") else str(memory_type)
        query = {
            "user_id": user_id,
            "type": type_val,
            "status": "active",
            "$or": [
                {"expires_at": None},
                {"expires_at": {"$exists": False}},
                {"expires_at": {"$gt": now}},
            ],
        }
        cursor = self.db.memories.find(query)
        return [_clean_doc(doc) for doc in cursor if doc]

    def vector_index_status(self) -> str:
        """Inspect and return the vector search index status: 'missing', 'building', or 'ready'."""
        try:
            indexes = list(self.db.memories.list_search_indexes())
        except Exception as exc:
            logger.warning("Could not list search indexes: %s", exc)
            return "missing"

        target: Optional[dict[str, Any]] = None
        for idx in indexes:
            if idx.get("name") == self.strategy.index_name:
                target = idx
                break

        if target is None:
            return "missing"

        status_str = str(target.get("status", "")).upper()
        queryable = target.get("queryable")

        if status_str == "READY" or queryable is True:
            return "ready"
        return "building"

    def vector_search(
        self,
        query_text: str,
        user_id: str,
        limit: int = 10,
        memory_types: Optional[list[str]] = None,
        statuses: tuple[str, ...] = ("active",),
        num_candidates: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Execute vector search over user memories with expiration filtering and retry backoff."""
        status = self.vector_index_status()
        if status != "ready":
            raise VectorIndexNotReadyError(
                f"Vector search index '{self.strategy.index_name}' is not ready (status: '{status}')."
            )

        pipeline = build_vector_search_pipeline(
            strategy=self.strategy,
            query_text=query_text,
            user_id=user_id,
            limit=limit,
            memory_types=memory_types,
            statuses=statuses,
            num_candidates=num_candidates,
        )

        def _execute_search() -> list[dict[str, Any]]:
            try:
                cursor = self.db.memories.aggregate(pipeline)
                return [_clean_doc(doc) for doc in cursor if doc]
            except Exception as exc:
                if is_rate_limit_error(exc):
                    raise RateLimitError(str(exc)) from exc
                raise

        retrieved = run_with_backoff(
            _execute_search,
            max_attempts=3,
            base_delay=0.5,
            retryable_exceptions=(RateLimitError,),
        )

        logger.info(
            "Vector search executed for user_id=%s, retrieved %d candidates",
            user_id,
            len(retrieved),
        )
        return retrieved

    def ensure_indexes(self) -> None:
        """Create necessary vector search, TTL, compound, and unique indexes idempotently."""
        version_parts = []
        for p in pymongo.__version__.split(".")[:2]:
            try:
                version_parts.append(int(p))
            except ValueError:
                break
        if len(version_parts) >= 2 and tuple(version_parts[:2]) < (4, 7):
            raise RuntimeError(
                f"PyMongo 4.7 or newer is required for Automated Embedding index creation. Found version {pymongo.__version__}."
            )

        # Ensure collections exist in database before creating search indexes
        existing_collections = self.db.list_collection_names()
        for coll_name in ["memories", "users", "messages"]:
            if coll_name not in existing_collections:
                self.db.create_collection(coll_name)

        existing_search: list[dict[str, Any]] = []
        try:
            existing_search = list(self.db.memories.list_search_indexes())
        except Exception as exc:
            logger.warning("Could not check existing search indexes: %s", exc)

        index_exists = any(
            idx.get("name") == self.strategy.index_name for idx in existing_search
        )
        if not index_exists:
            from pymongo.operations import SearchIndexModel
            index_def = self.strategy.build_index_definition(
                filter_paths=["user_id", "status", "type"]
            )
            model = SearchIndexModel(
                definition=index_def,
                name=self.strategy.index_name,
                type="vectorSearch",
            )
            self.db.memories.create_search_index(model=model)
            logger.info("Initiated creation of vector search index '%s'", self.strategy.index_name)

        # TTL index on expires_at
        self.db.memories.create_index([("expires_at", 1)], expireAfterSeconds=0, background=True)

        # Compound index on memories {user_id, status, type}
        self.db.memories.create_index(
            [("user_id", 1), ("status", 1), ("type", 1)],
            background=True,
        )

        # Unique index on users.user_id
        self.db.users.create_index([("user_id", 1)], unique=True, background=True)

        # Unique index on users.email (sparse to support legacy accounts without email)
        self.db.users.create_index([("email", 1)], unique=True, sparse=True, background=True)

        # Compound index on messages {session_id, created_at}
        self.db.messages.create_index(
            [("session_id", 1), ("created_at", 1)],
            background=True,
        )

    def update_fields(
        self,
        memory_id: str,
        user_id: str,
        fields: dict[str, Any],
    ) -> bool:
        """Update specific fields of a memory scoped by user_id and set updated_at."""
        update_doc = dict(fields)
        update_doc["updated_at"] = utc_now()
        res = self.db.memories.update_one(
            {"_id": memory_id, "user_id": user_id},
            {"$set": update_doc},
        )
        return res.matched_count > 0

    def link_supersede(
        self,
        old_id: str,
        new_id: str,
        user_id: str,
    ) -> bool:
        """Link an old memory to its superseding version in a transaction or safe order."""
        now = utc_now()
        new_update = {"supersedes": old_id, "updated_at": now}
        old_update = {
            "status": MemoryStatus.SUPERSEDED.value,
            "superseded_by": new_id,
            "updated_at": now,
        }

        client = getattr(self.db, "client", None)
        if client is not None and hasattr(client, "start_session"):
            try:
                with client.start_session() as session:
                    with session.start_transaction():
                        res_new = self.db.memories.update_one(
                            {"_id": new_id, "user_id": user_id},
                            {"$set": new_update},
                            session=session,
                        )
                        res_old = self.db.memories.update_one(
                            {"_id": old_id, "user_id": user_id},
                            {"$set": old_update},
                            session=session,
                        )
                        return res_old.matched_count > 0 and res_new.matched_count > 0
            except Exception as exc:
                logger.debug("Transaction not supported or failed, falling back to safe ordering: %s", exc)

        # Fallback safe ordering
        self.db.memories.update_one(
            {"_id": new_id, "user_id": user_id},
            {"$set": new_update},
        )
        res_old = self.db.memories.update_one(
            {"_id": old_id, "user_id": user_id},
            {"$set": old_update},
        )
        return res_old.matched_count > 0

    def soft_delete(
        self,
        memory_id: str,
        user_id: str,
        now: Optional[datetime] = None,
    ) -> bool:
        """Soft delete a memory by setting status to deleted, deleted_at, and unsetting embedding."""
        ts = now if now is not None else utc_now()
        res = self.db.memories.update_one(
            {"_id": memory_id, "user_id": user_id},
            {
                "$set": {
                    "status": MemoryStatus.DELETED.value,
                    "deleted_at": ts,
                    "updated_at": ts,
                },
                "$unset": {"embedding": ""},
            },
        )
        return res.matched_count > 0

    def hard_delete(self, memory_id: str, user_id: str) -> bool:
        """Permanently remove a memory document scoped by user_id."""
        res = self.db.memories.delete_one({"_id": memory_id, "user_id": user_id})
        return res.deleted_count > 0

    def find_duplicate_candidates(
        self,
        user_id: str,
        type: MemoryType | str,
        normalized_key: str,
        now: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Find active, non-expired memories with the same type and matching normalized structured key."""
        ts = now if now is not None else utc_now()
        type_val = type.value if hasattr(type, "value") else str(type)
        query = {
            "user_id": user_id,
            "type": type_val,
            "status": "active",
            "$or": [
                {"expires_at": None},
                {"expires_at": {"$exists": False}},
                {"expires_at": {"$gt": ts}},
            ],
            "$and": [
                {
                    "$or": [
                        {"dedupe_key": normalized_key},
                        {"structured._dedupe_key": normalized_key},
                    ]
                }
            ],
        }
        cursor = self.db.memories.find(query)
        return [_clean_doc(doc) for doc in cursor if doc]

    def find_expired(
        self,
        user_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Find active memories whose expires_at is less than or equal to now."""
        ts = now if now is not None else utc_now()
        query: dict[str, Any] = {
            "status": "active",
            "expires_at": {"$lte": ts},
        }
        if user_id:
            query["user_id"] = user_id

        cursor = self.db.memories.find(query)
        return [_clean_doc(doc) for doc in cursor if doc]

    def get_memory_by_id_scoped(
        self,
        memory_id: str,
        user_id: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve a memory document by ID scoped strictly to user_id (no cross-user access)."""
        doc = self.db.memories.find_one({"_id": memory_id, "user_id": user_id})
        return _clean_doc(doc)

