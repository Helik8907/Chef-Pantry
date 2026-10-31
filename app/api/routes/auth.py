"""Authentication API routes for Memory Chef."""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import get_user_repository
from app.domain.models import (
    DeleteAccountResponse,
    LogoutResponse,
    TokenResponse,
    User,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.infra.repositories.user_repository import UserRepository
from app.services.auth import (
    authenticate_user,
    create_access_token,
    delete_user_account,
    register_user,
    verify_access_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    user_repo: UserRepository = Depends(get_user_repository),
) -> User:
    """Dependency to retrieve the currently authenticated user from Bearer token."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials are required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = verify_access_token(credentials.credentials)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    doc = user_repo.get_user(token_data["user_id"])
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authenticated user account no longer exists.",
        )
    return User.model_validate(doc)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description="Registers a user account using email and password, returning an access token and profile.",
)
def register(
    payload: UserRegisterRequest,
    user_repo: UserRepository = Depends(get_user_repository),
) -> TokenResponse:
    """Register a new user and generate an initial access token."""
    try:
        user = register_user(
            user_repo=user_repo,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            user_id=payload.user_id,
            settings=payload.settings,
        )
    except ValueError as exc:
        err_msg = str(exc)
        status_code = status.HTTP_409_CONFLICT if "already" in err_msg.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=err_msg)

    token = create_access_token(user_id=user.user_id, email=user.email)
    return TokenResponse(access_token=token, token_type="bearer", user=user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate user with email and password",
    description="Authenticates credentials and returns a signed bearer access token.",
)
def login(
    payload: UserLoginRequest,
    user_repo: UserRepository = Depends(get_user_repository),
) -> TokenResponse:
    """Authenticate user with email and password."""
    user = authenticate_user(
        user_repo=user_repo,
        email=payload.email,
        password=payload.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user_id=user.user_id, email=user.email)
    return TokenResponse(access_token=token, token_type="bearer", user=user)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Log out active session",
    description="Logs out the current session and acknowledges session termination.",
)
def logout(
    current_user: User = Depends(get_current_user),
) -> LogoutResponse:
    """Acknowledge session termination and logout."""
    return LogoutResponse(status="logged_out", user_id=current_user.user_id)


@router.get(
    "/me",
    response_model=User,
    summary="Get current user profile",
    description="Retrieves the profile of the currently authenticated user.",
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return profile for the currently authenticated user."""
    return current_user


@router.delete(
    "/account",
    response_model=DeleteAccountResponse,
    summary="Delete current user account",
    description="Permanently deletes the authenticated user's account and all associated memories and chat messages.",
)
def delete_account(
    cascade: bool = Query(default=True, description="Whether to cascade delete memories and messages."),
    current_user: User = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repository),
) -> DeleteAccountResponse:
    """Permanently delete authenticated user account."""
    success = delete_user_account(user_repo=user_repo, identifier=current_user.user_id, cascade=cascade)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account.",
        )
    return DeleteAccountResponse(status="deleted", user_id=current_user.user_id, cascade=cascade)
