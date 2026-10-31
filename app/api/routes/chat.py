"""Chat session routes for Memory Chef."""

from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import get_message_repository, get_user_repository
from app.domain.models import Message, utc_now
from app.infra.repositories.message_repository import MessageRepository
from app.infra.repositories.user_repository import UserRepository
from app.services.chat_orchestrator import _dict_to_message

router = APIRouter(prefix="/chat", tags=["chat"])


class SessionSummary(BaseModel):
    """Summary metadata for a chat session."""

    session_id: str = Field(..., description="Unique session identifier.")
    first_message_time: Optional[datetime] = Field(default=None, description="Timestamp of first message in UTC.")
    last_message_time: Optional[datetime] = Field(default=None, description="Timestamp of latest message in UTC.")
    message_count: int = Field(default=0, ge=0, description="Total messages in the session.")


class SessionDetailResponse(BaseModel):
    """Detailed conversation history for a specific chat session."""

    session_id: str = Field(..., description="Unique session identifier.")
    user_id: str = Field(..., description="Associated user identifier.")
    message_count: int = Field(..., ge=0, description="Number of messages in the session.")
    messages: list[Message] = Field(default_factory=list, description="Ordered conversation messages.")


class CreateSessionRequest(BaseModel):
    """Request payload to create or initialize a chat session."""

    user_id: str = Field(..., min_length=1, max_length=100, description="Unique user identifier.")
    session_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Optional custom session identifier. If omitted, a unique ID is auto-generated.",
    )


class CreateSessionResponse(BaseModel):
    """Response payload when a new chat session is created."""

    session_id: str = Field(..., description="Unique session identifier.")
    user_id: str = Field(..., description="Associated user identifier.")
    created_at: datetime = Field(default_factory=utc_now, description="Session creation timestamp in UTC.")
    status: str = Field(default="created", description="Session creation status.")


class DeleteSessionResponse(BaseModel):
    """Response payload when a chat session is deleted."""

    status: str = Field(default="deleted", description="Operation status.")
    session_id: str = Field(..., description="Identifier of the deleted session.")
    user_id: str = Field(..., description="Identifier of the user who owned the session.")
    deleted_count: int = Field(..., ge=0, description="Total number of deleted message documents.")


@router.get(
    "/sessions",
    response_model=list[SessionSummary],
    summary="List chat sessions for a user",
    description="Retrieves a list of previous chat sessions for a user with first/last message timestamps and message counts.",
)
def list_user_sessions(
    user_id: str = Query(..., min_length=1, max_length=100, description="User handle to list sessions for."),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of sessions to return."),
    user_repo: UserRepository = Depends(get_user_repository),
    message_repo: MessageRepository = Depends(get_message_repository),
) -> list[SessionSummary]:
    """List previous chat sessions for a user."""
    user = user_repo.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found.",
        )

    raw_sessions = message_repo.list_sessions(user_id=user_id, limit=limit)
    return [SessionSummary.model_validate(s) for s in raw_sessions]


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get old chat session history",
    description="Retrieves all messages for a specific chat session ordered from oldest to newest. Returns 404 if no session messages exist.",
)
def get_session_history(
    session_id: str,
    user_id: str = Query(..., min_length=1, max_length=100, description="User handle for session scoping."),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum number of messages to return."),
    user_repo: UserRepository = Depends(get_user_repository),
    message_repo: MessageRepository = Depends(get_message_repository),
) -> SessionDetailResponse:
    """Retrieve message history for a specific chat session."""
    user = user_repo.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found.",
        )

    raw_messages = message_repo.list_messages(user_id=user_id, session_id=session_id, limit=limit)
    if not raw_messages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session '{session_id}' not found for user '{user_id}'.",
        )

    messages = [_dict_to_message(doc) for doc in raw_messages]
    return SessionDetailResponse(
        session_id=session_id,
        user_id=user_id,
        message_count=len(messages),
        messages=messages,
    )


@router.post(
    "/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
    description="Initializes a new chat session identifier for the specified user.",
)
def create_session(
    payload: CreateSessionRequest,
    user_repo: UserRepository = Depends(get_user_repository),
) -> CreateSessionResponse:
    """Initialize a new chat session."""
    user = user_repo.get_user(payload.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{payload.user_id}' not found.",
        )

    session_id = payload.session_id or f"session_{uuid.uuid4().hex[:12]}"
    return CreateSessionResponse(
        session_id=session_id,
        user_id=payload.user_id,
        created_at=utc_now(),
        status="created",
    )


@router.delete(
    "/sessions/{session_id}",
    response_model=DeleteSessionResponse,
    summary="Delete a chat session",
    description="Permanently deletes a chat session and all associated messages for a user. Returns 404 if the session does not exist.",
)
def delete_session(
    session_id: str,
    user_id: str = Query(..., min_length=1, max_length=100, description="User handle for session scoping."),
    user_repo: UserRepository = Depends(get_user_repository),
    message_repo: MessageRepository = Depends(get_message_repository),
) -> DeleteSessionResponse:
    """Delete a chat session and all its messages."""
    user = user_repo.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found.",
        )

    deleted_count = message_repo.delete_session(user_id=user_id, session_id=session_id)
    if deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session '{session_id}' not found for user '{user_id}'.",
        )

    return DeleteSessionResponse(
        status="deleted",
        session_id=session_id,
        user_id=user_id,
        deleted_count=deleted_count,
    )
