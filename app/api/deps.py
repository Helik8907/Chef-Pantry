"""FastAPI dependencies and container retrieval for Memory Chef API."""

from typing import Optional
from app.infra.memory_repository import MemoryRepository
from app.infra.repositories.message_repository import MessageRepository
from app.infra.repositories.user_repository import UserRepository
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.container import Container, build_container

_container: Optional[Container] = None


def get_container() -> Container:
    """Retrieve or initialize application Container singleton."""
    global _container
    if _container is None:
        _container = build_container()
    return _container


def set_container(container: Optional[Container]) -> None:
    """Explicitly set or reset the container instance (e.g. for unit testing)."""
    global _container
    _container = container


def get_repository() -> MemoryRepository:
    """FastAPI dependency providing unified MemoryRepository facade from active container."""
    return get_container().repository


def get_user_repository() -> UserRepository:
    """FastAPI dependency providing dedicated UserRepository."""
    container = get_container()
    if hasattr(container.repository, "user_repo"):
        return container.repository.user_repo
    return UserRepository(db=container.db)


def get_message_repository() -> MessageRepository:
    """FastAPI dependency providing dedicated MessageRepository."""
    container = get_container()
    if hasattr(container.repository, "message_repo"):
        return container.repository.message_repo
    return MessageRepository(db=container.db)


def get_orchestrator() -> ChatOrchestrator:
    """FastAPI dependency providing ChatOrchestrator service."""
    return get_container().orchestrator

