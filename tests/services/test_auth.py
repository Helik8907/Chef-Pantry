"""Unit tests for authentication and password management services."""

from typing import Any, Optional
import pytest

from app.domain.models import User, UserSettings, utc_now
from app.services.auth import (
    authenticate_user,
    create_access_token,
    delete_user_account,
    hash_password,
    register_user,
    verify_access_token,
    verify_password,
)


class MockUserRepository:
    """In-memory mock user repository for offline auth tests."""

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
        if hasattr(user, "model_dump"):
            doc = user.model_dump(by_alias=True)
            if hasattr(user, "password_hash") and user.password_hash is not None:
                doc["password_hash"] = user.password_hash
        else:
            doc = dict(user)

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


def test_password_hashing_and_verification() -> None:
    """Test PBKDF2 password hashing and verification."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed.startswith("pbkdf2:sha256:")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(password, "") is False
    assert verify_password(password, "malformed_hash") is False


def test_password_hashing_empty_raises() -> None:
    """Test that hashing an empty password raises ValueError."""
    with pytest.raises(ValueError, match="Password cannot be empty"):
        hash_password("")


def test_token_creation_and_validation() -> None:
    """Test access token generation, HMAC signature check, and payload decoding."""
    user_id = "chef_julia"
    email = "julia@childs.com"
    token = create_access_token(user_id=user_id, email=email)

    assert isinstance(token, str)
    decoded = verify_access_token(token)
    assert decoded is not None
    assert decoded["user_id"] == user_id
    assert decoded["email"] == email

    # Tampered token check
    tampered = token[:-4] + "abcd"
    assert verify_access_token(tampered) is None
    assert verify_access_token("invalid:token") is None
    assert verify_access_token("") is None


def test_register_user_success() -> None:
    """Test user registration with valid credentials and handle generation."""
    repo = MockUserRepository()

    user = register_user(
        user_repo=repo,
        email="ALICE@EXAMPLE.COM",
        password="MySecretPassword123",
        display_name="Alice Waters",
        user_id="alice_w",
    )

    assert user.user_id == "alice_w"
    assert user.email == "alice@example.com"
    assert user.display_name == "Alice Waters"
    assert user.password_hash is not None
    assert user.password_hash.startswith("pbkdf2:sha256:")
    assert verify_password("MySecretPassword123", user.password_hash) is True


def test_register_user_auto_handle() -> None:
    """Test user registration with auto-derived user handle from email."""
    repo = MockUserRepository()

    user = register_user(
        user_repo=repo,
        email="gordon.ramsay@hellskitchen.com",
        password="HellKitchenPass123",
        display_name="Gordon Ramsay",
    )

    assert "gordon" in user.user_id
    assert user.email == "gordon.ramsay@hellskitchen.com"


def test_register_user_duplicate_email_fails() -> None:
    """Test that duplicate email registrations are prevented."""
    repo = MockUserRepository()

    register_user(
        user_repo=repo,
        email="chef@pantry.com",
        password="ValidPassword123",
        display_name="Chef One",
        user_id="chef1",
    )

    with pytest.raises(ValueError, match="already exists"):
        register_user(
            user_repo=repo,
            email="chef@pantry.com",
            password="AnotherPassword123",
            display_name="Chef Two",
            user_id="chef2",
        )


def test_register_user_duplicate_handle_fails() -> None:
    """Test that duplicate username handles are rejected."""
    repo = MockUserRepository()

    register_user(
        user_repo=repo,
        email="user1@pantry.com",
        password="ValidPassword123",
        display_name="User One",
        user_id="same_handle",
    )

    with pytest.raises(ValueError, match="already in use"):
        register_user(
            user_repo=repo,
            email="user2@pantry.com",
            password="ValidPassword123",
            display_name="User Two",
            user_id="same_handle",
        )


def test_authenticate_user_success_and_failure() -> None:
    """Test email/password authentication outcomes."""
    repo = MockUserRepository()

    register_user(
        user_repo=repo,
        email="login_user@example.com",
        password="CorrectPassword123",
        display_name="Login Test User",
        user_id="login_tester",
    )

    # Valid credentials
    auth_user = authenticate_user(repo, "login_user@example.com", "CorrectPassword123")
    assert auth_user is not None
    assert auth_user.user_id == "login_tester"

    # Case-insensitive email
    auth_user_upper = authenticate_user(repo, "LOGIN_USER@EXAMPLE.COM", "CorrectPassword123")
    assert auth_user_upper is not None

    # Invalid password
    assert authenticate_user(repo, "login_user@example.com", "WrongPassword") is None

    # Non-existent email
    assert authenticate_user(repo, "unknown@example.com", "CorrectPassword123") is None

    # Empty inputs
    assert authenticate_user(repo, "", "CorrectPassword123") is None
    assert authenticate_user(repo, "login_user@example.com", "") is None


def test_delete_user_account() -> None:
    """Test account deletion."""
    repo = MockUserRepository()

    register_user(
        user_repo=repo,
        email="delete_me@example.com",
        password="Password123!",
        display_name="Delete Target",
        user_id="delete_target",
    )

    assert repo.get_user("delete_target") is not None
    deleted = delete_user_account(repo, "delete_target", cascade=True)
    assert deleted is True
    assert repo.get_user("delete_target") is None
