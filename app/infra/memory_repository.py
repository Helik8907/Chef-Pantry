"""Unified memory repository facade providing backward compatibility for Memory Chef services."""

from typing import Any, Optional
from pymongo.database import Database

from app.infra.providers.base import VectorStrategy
from app.infra.repositories.base import (
    RateLimitError,
    VectorIndexNotReadyError,
    build_vector_search_pipeline,
    is_rate_limit_error as _is_rate_limit_error,
)
from app.infra.repositories.memory_repository import MemoryRepository as MemoryRepositoryCore
from app.infra.repositories.message_repository import MessageRepository
from app.infra.repositories.user_repository import UserRepository


class MemoryRepository(MemoryRepositoryCore):
    """Unified repository facade aggregating memory, user, and message operations."""

    def __init__(self, db: Database, strategy: VectorStrategy) -> None:
        super().__init__(db=db, strategy=strategy)
        self.user_repo = UserRepository(db=db)
        self.message_repo = MessageRepository(db=db)

    # --- User operations delegation ---
    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        """Retrieve user document by user_id or email."""
        return self.user_repo.get_user(user_id)

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        """Retrieve user document by email address."""
        return self.user_repo.get_user_by_email(email)

    def upsert_user(self, user: Any) -> dict[str, Any]:
        """Upsert user profile document by user_id and return persisted record."""
        return self.user_repo.upsert_user(user)

    def delete_user(self, user_id: str, cascade: bool = True) -> bool:
        """Permanently remove a user record and optionally cascade delete their memories and messages."""
        return self.user_repo.delete_user(user_id=user_id, cascade=cascade)

    # --- Message operations delegation ---
    def insert_message(self, message: Any) -> str:
        """Persist a chat message record and return its ID string."""
        return self.message_repo.insert_message(message)

    def list_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent session messages ordered from oldest to newest."""
        return self.message_repo.list_messages(user_id=user_id, session_id=session_id, limit=limit)

    def list_sessions(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List distinct user chat sessions with first/last message times and total count."""
        return self.message_repo.list_sessions(user_id=user_id, limit=limit)

    def delete_session(self, user_id: str, session_id: str) -> int:
        """Permanently delete all messages in a session for a user and return deleted count."""
        return self.message_repo.delete_session(user_id=user_id, session_id=session_id)



__all__ = [
    "MemoryRepository",
    "VectorIndexNotReadyError",
    "RateLimitError",
    "_is_rate_limit_error",
    "build_vector_search_pipeline",
]
