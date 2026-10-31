"""Unit tests for FastAPI authentication routes."""

from typing import Any, Optional
import pytest
from fastapi import HTTPException

from app.api.routes.auth import (
    delete_account,
    get_current_user,
    get_me,
    login,
    logout,
    register,
)
from app.domain.models import (
    User,
    UserLoginRequest,
    UserRegisterRequest,
    UserSettings,
)
from app.services.auth import create_access_token, hash_password


class MockUserRepoForRoutes:
    """Mock user repository for auth route tests."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}

    def get_user(self, identifier: str) -> Optional[dict[str, Any]]:
        clean = identifier.strip().lower()
        for doc in self.users.values():
            if (
                doc.get("user_id") == identifier
                or str(doc.get("email", "")).lower() == clean
                or str(doc.get("_id")) == identifier
            ):
                return dict(doc)
        return None

    def upsert_user(self, user: Any) -> dict[str, Any]:
        doc = user.model_dump(by_alias=True) if hasattr(user, "model_dump") else dict(user)
        if hasattr(user, "password_hash") and user.password_hash is not None:
            doc["password_hash"] = user.password_hash
        user_id = doc["user_id"]
        if doc.get("email"):
            doc["email"] = doc["email"].strip().lower()
        self.users[user_id] = doc
        return dict(doc)

    def delete_user(self, identifier: str, cascade: bool = True) -> bool:
        doc = self.get_user(identifier)
        if not doc:
            return False
        user_id = doc["user_id"]
        return self.users.pop(user_id, None) is not None


class DummyCredentials:
    """Mock HTTPAuthorizationCredentials."""

    def __init__(self, token: str) -> None:
        self.credentials = token


def test_route_register_success() -> None:
    """Test successful user registration route."""
    repo = MockUserRepoForRoutes()
    req = UserRegisterRequest(
        email="chef_test@example.com",
        password="SecurePassword123",
        display_name="Chef Tester",
        user_id="cheftester",
    )

    resp = register(payload=req, user_repo=repo)
    assert resp.access_token is not None
    assert resp.token_type == "bearer"
    assert resp.user.user_id == "cheftester"
    assert resp.user.email == "chef_test@example.com"


def test_route_register_duplicate_conflict() -> None:
    """Test duplicate registration triggers 409 Conflict."""
    repo = MockUserRepoForRoutes()
    req = UserRegisterRequest(
        email="chef_dupe@example.com",
        password="SecurePassword123",
        display_name="Chef Dupe",
        user_id="chefdupe",
    )
    register(payload=req, user_repo=repo)

    with pytest.raises(HTTPException) as exc_info:
        register(payload=req, user_repo=repo)
    assert exc_info.value.status_code == 409


def test_route_login_success_and_failure() -> None:
    """Test login route authentication."""
    repo = MockUserRepoForRoutes()
    reg_req = UserRegisterRequest(
        email="login_route@example.com",
        password="CorrectPassword123",
        display_name="Login Route User",
        user_id="loginroute",
    )
    register(payload=reg_req, user_repo=repo)

    # Valid login
    login_req = UserLoginRequest(email="login_route@example.com", password="CorrectPassword123")
    resp = login(payload=login_req, user_repo=repo)
    assert resp.access_token is not None
    assert resp.user.user_id == "loginroute"

    # Invalid password raises 401
    bad_login = UserLoginRequest(email="login_route@example.com", password="WrongPassword")
    with pytest.raises(HTTPException) as exc_info:
        login(payload=bad_login, user_repo=repo)
    assert exc_info.value.status_code == 401


def test_route_get_me_and_current_user_dependency() -> None:
    """Test token resolution via get_current_user and profile retrieval via get_me."""
    repo = MockUserRepoForRoutes()
    reg_req = UserRegisterRequest(
        email="me_route@example.com",
        password="Password123!",
        display_name="Me Route",
        user_id="meroute",
    )
    reg_resp = register(payload=reg_req, user_repo=repo)

    creds = DummyCredentials(reg_resp.access_token)
    current_user = get_current_user(credentials=creds, user_repo=repo)
    assert current_user.user_id == "meroute"

    me_resp = get_me(current_user=current_user)
    assert me_resp.user_id == "meroute"


def test_route_logout() -> None:
    """Test logout route."""
    user = User(user_id="logout_user", email="out@test.com", display_name="Logout User")
    resp = logout(current_user=user)
    assert resp.status == "logged_out"
    assert resp.user_id == "logout_user"


def test_route_delete_account() -> None:
    """Test account deletion route."""
    repo = MockUserRepoForRoutes()
    reg_req = UserRegisterRequest(
        email="del_route@example.com",
        password="Password123!",
        display_name="Delete Route",
        user_id="delroute",
    )
    register(payload=reg_req, user_repo=repo)

    user = User.model_validate(repo.get_user("delroute"))
    resp = delete_account(cascade=True, current_user=user, user_repo=repo)
    assert resp.status == "deleted"
    assert resp.user_id == "delroute"
    assert repo.get_user("delroute") is None
