"""User management routes for Memory Chef."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import get_user_repository
from app.domain.models import User, UserSettings
from app.infra.repositories.user_repository import UserRepository

router = APIRouter(prefix="/users", tags=["users"])


class UserCreateRequest(BaseModel):
    """Payload schema for creating a new user."""

    user_id: str = Field(..., min_length=1, max_length=100, description="Unique user handle.")
    email: Optional[str] = Field(default=None, description="Optional user email address.")
    display_name: str = Field(..., min_length=1, max_length=100, description="Human-readable user display name.")
    settings: Optional[UserSettings] = Field(default=None, description="Optional user preferences.")


class DeleteUserResponse(BaseModel):
    """Response schema for user deletion."""

    status: str = Field(default="deleted", description="Operation status.")
    user_id: str = Field(..., description="Deleted user identifier.")
    cascade: bool = Field(..., description="Whether associated memories and messages were cascade deleted.")


@router.post(
    "",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description="Registers a new user record. Returns 409 Conflict if user_id or email already exists.",
)
def create_user(
    payload: UserCreateRequest,
    repo: UserRepository = Depends(get_user_repository),
) -> User:
    """Create a new user record."""
    existing = repo.get_user(payload.user_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with user_id '{payload.user_id}' already exists.",
        )

    if payload.email:
        existing_email = repo.get_user(payload.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with email '{payload.email}' already exists.",
            )

    user = User(
        user_id=payload.user_id,
        email=payload.email,
        display_name=payload.display_name,
        settings=payload.settings or UserSettings(),
    )
    try:
        persisted = repo.upsert_user(user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return User.model_validate(persisted)


@router.get(
    "/{user_id}",
    response_model=User,
    summary="Get user profile",
    description="Retrieves a user profile by user_id. Returns 404 Not Found if user does not exist.",
)
def get_user(
    user_id: str,
    repo: UserRepository = Depends(get_user_repository),
) -> User:
    """Retrieve user profile by unique user handle."""
    doc = repo.get_user(user_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found.",
        )
    return User.model_validate(doc)


@router.delete(
    "/{user_id}",
    response_model=DeleteUserResponse,
    summary="Delete a user",
    description="Permanently deletes a user. When cascade=true (default), also deletes associated memories and messages.",
)
def delete_user(
    user_id: str,
    cascade: bool = Query(default=True, description="Whether to cascade delete memories and messages."),
    repo: UserRepository = Depends(get_user_repository),
) -> DeleteUserResponse:
    """Permanently delete user and optionally cascade delete their memories and messages."""
    doc = repo.get_user(user_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found.",
        )

    repo.delete_user(user_id, cascade=cascade)
    return DeleteUserResponse(status="deleted", user_id=user_id, cascade=cascade)
