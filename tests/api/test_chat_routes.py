"""Offline unit tests for chat session routes."""

from datetime import datetime, timezone
from typing import Any, Optional
import pytest
from fastapi import HTTPException

from app.api.routes.chat import (
    CreateSessionRequest,
    create_session,
    delete_session,
    get_session_history,
    list_user_sessions,
)
from app.domain.models import Message, MessageRole, User, UserSettings, utc_now


class FakeUserRepository:
    """In-memory user repository test double."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        return self.users.get(user_id)

    def upsert_user(self, user: Any) -> dict[str, Any]:
        doc = user.model_dump(by_alias=True) if hasattr(user, "model_dump") else dict(user)
        self.users[doc["user_id"]] = doc
        return doc

    def delete_user(self, user_id: str, cascade: bool = True) -> bool:
        return self.users.pop(user_id, None) is not None


class FakeMessageRepository:
    """In-memory message repository test double."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def insert_message(self, message: Any) -> str:
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
        matched = [
            m for m in self.messages
            if m.get("user_id") == user_id and m.get("session_id") == session_id
        ]
        return matched[:limit]

    def list_sessions(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        user_msgs = [m for m in self.messages if m.get("user_id") == user_id]
        by_session: dict[str, list[dict[str, Any]]] = {}
        for m in user_msgs:
            sid = m.get("session_id", "")
            by_session.setdefault(sid, []).append(m)

        results = []
        for sid, msgs in by_session.items():
            results.append({
                "session_id": sid,
                "first_message_time": msgs[0].get("created_at"),
                "last_message_time": msgs[-1].get("created_at"),
                "message_count": len(msgs),
            })
        return results[:limit]

    def delete_session(self, user_id: str, session_id: str) -> int:
        before_count = len(self.messages)
        self.messages = [
            m for m in self.messages
            if not (m.get("user_id") == user_id and m.get("session_id") == session_id)
        ]
        return before_count - len(self.messages)


@pytest.fixture
def repos():
    """Create test repositories for route tests."""
    fake_user_repo = FakeUserRepository()
    fake_msg_repo = FakeMessageRepository()
    return fake_user_repo, fake_msg_repo


def test_create_session_success(repos):
    user_repo, _ = repos
    user_repo.upsert_user(User(user_id="chef_dan", display_name="Chef Dan"))

    # Auto-generated session ID
    res = create_session(CreateSessionRequest(user_id="chef_dan"), user_repo=user_repo)
    assert res.user_id == "chef_dan"
    assert res.session_id.startswith("session_")
    assert res.status == "created"

    # Custom session ID
    res2 = create_session(CreateSessionRequest(user_id="chef_dan", session_id="dinner_party_2026"), user_repo=user_repo)
    assert res2.session_id == "dinner_party_2026"
    assert res2.user_id == "chef_dan"


def test_create_session_user_not_found(repos):
    user_repo, _ = repos
    with pytest.raises(HTTPException) as exc_info:
        create_session(CreateSessionRequest(user_id="ghost_user"), user_repo=user_repo)
    assert exc_info.value.status_code == 404
    assert "User 'ghost_user' not found" in exc_info.value.detail


def test_list_user_sessions_empty_and_populated(repos):
    user_repo, msg_repo = repos
    user_repo.upsert_user(User(user_id="chef_maria", display_name="Maria"))

    # Empty sessions list
    sessions = list_user_sessions(user_id="chef_maria", limit=50, user_repo=user_repo, message_repo=msg_repo)
    assert sessions == []

    # Insert messages for two sessions
    now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    msg_repo.insert_message({
        "user_id": "chef_maria",
        "session_id": "sess_1",
        "role": "user",
        "content": "Hi chef!",
        "created_at": now,
    })
    msg_repo.insert_message({
        "user_id": "chef_maria",
        "session_id": "sess_1",
        "role": "assistant",
        "content": "Hello Maria!",
        "created_at": now,
    })
    msg_repo.insert_message({
        "user_id": "chef_maria",
        "session_id": "sess_2",
        "role": "user",
        "content": "Quick breakfast ideas?",
        "created_at": now,
    })

    sessions = list_user_sessions(user_id="chef_maria", limit=50, user_repo=user_repo, message_repo=msg_repo)
    assert len(sessions) == 2
    sess_1 = next(s for s in sessions if s.session_id == "sess_1")
    assert sess_1.message_count == 2


def test_list_user_sessions_user_not_found(repos):
    user_repo, msg_repo = repos
    with pytest.raises(HTTPException) as exc_info:
        list_user_sessions(user_id="unknown_user", limit=50, user_repo=user_repo, message_repo=msg_repo)
    assert exc_info.value.status_code == 404


def test_get_session_history_success_and_not_found(repos):
    user_repo, msg_repo = repos
    user_repo.upsert_user(User(user_id="user_history", display_name="History User"))

    # Session not found
    with pytest.raises(HTTPException) as exc_info:
        get_session_history(session_id="sess_missing", user_id="user_history", limit=100, user_repo=user_repo, message_repo=msg_repo)
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()

    # Add message and verify retrieval
    msg_repo.insert_message({
        "user_id": "user_history",
        "session_id": "sess_found",
        "role": "user",
        "content": "What can I cook with tomatoes?",
        "created_at": datetime(2026, 10, 31, 10, 0, 0, tzinfo=timezone.utc),
    })

    data = get_session_history(session_id="sess_found", user_id="user_history", limit=100, user_repo=user_repo, message_repo=msg_repo)
    assert data.session_id == "sess_found"
    assert data.user_id == "user_history"
    assert data.message_count == 1
    assert data.messages[0].content == "What can I cook with tomatoes?"


def test_delete_session_success_and_not_found(repos):
    user_repo, msg_repo = repos
    user_repo.upsert_user(User(user_id="chef_alex", display_name="Alex"))

    # Delete non-existent session
    with pytest.raises(HTTPException) as exc_info:
        delete_session(session_id="sess_ghost", user_id="chef_alex", user_repo=user_repo, message_repo=msg_repo)
    assert exc_info.value.status_code == 404

    # Seed messages
    msg_repo.insert_message({
        "user_id": "chef_alex",
        "session_id": "sess_to_delete",
        "role": "user",
        "content": "Message 1",
        "created_at": utc_now(),
    })
    msg_repo.insert_message({
        "user_id": "chef_alex",
        "session_id": "sess_to_delete",
        "role": "assistant",
        "content": "Message 2",
        "created_at": utc_now(),
    })

    # Delete existing session
    res = delete_session(session_id="sess_to_delete", user_id="chef_alex", user_repo=user_repo, message_repo=msg_repo)
    assert res.status == "deleted"
    assert res.session_id == "sess_to_delete"
    assert res.user_id == "chef_alex"
    assert res.deleted_count == 2

    # Verifying it's gone
    with pytest.raises(HTTPException) as exc_info:
        get_session_history(session_id="sess_to_delete", user_id="chef_alex", limit=100, user_repo=user_repo, message_repo=msg_repo)
    assert exc_info.value.status_code == 404
