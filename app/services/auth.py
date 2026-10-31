"""Authentication and password security service for Memory Chef."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import os
import re
import secrets
from typing import Any, Optional

from app.domain.models import User, UserSettings, utc_now

logger = logging.getLogger(__name__)

# Authentication secret for token signing (reads from env or uses deterministic project fallback)
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "chef-pantry-auth-secret-key-2026-secure")
TOKEN_EXPIRY_DAYS = 7
PBKDF2_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    """Hash a plaintext password using salted PBKDF2-HMAC-SHA256."""
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2:sha256:{PBKDF2_ITERATIONS}${salt.hex()}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against a stored PBKDF2 hash using constant-time comparison."""
    if not plain_password or not hashed_password:
        return False
    try:
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False
        header, salt_hex, key_hex = parts
        _, _, iterations_str = header.split(":")
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)

        actual_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual_key, expected_key)
    except Exception as exc:
        logger.warning("Password verification failed with error: %s", exc)
        return False


def create_access_token(user_id: str, email: Optional[str] = None) -> str:
    """Create a signed bearer session token with expiration timestamp."""
    exp_timestamp = int((datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRY_DAYS)).timestamp())
    nonce = secrets.token_hex(8)
    clean_email = (email or "").strip().lower()
    payload = f"{user_id}:{clean_email}:{exp_timestamp}:{nonce}"
    signature = hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}:{signature}"


def verify_access_token(token: str) -> Optional[dict[str, Any]]:
    """Validate token signature and expiration, returning decoded session payload or None."""
    if not token or not isinstance(token, str):
        return None
    try:
        parts = token.strip().split(":")
        if len(parts) != 5:
            return None
        user_id, email, exp_str, nonce, signature = parts
        payload = f"{user_id}:{email}:{exp_str}:{nonce}"

        expected_sig = hmac.new(
            AUTH_SECRET_KEY.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return None

        exp_timestamp = int(exp_str)
        now_timestamp = int(datetime.now(timezone.utc).timestamp())
        if now_timestamp > exp_timestamp:
            return None

        return {
            "user_id": user_id,
            "email": email or None,
            "expires_at": datetime.fromtimestamp(exp_timestamp, timezone.utc),
        }
    except Exception as exc:
        logger.warning("Token verification encountered an error: %s", exc)
        return None


def authenticate_user(user_repo: Any, email: str, password: str) -> Optional[User]:
    """Authenticate user credentials by email and password."""
    if not email or not password:
        return None

    clean_email = email.strip().lower()
    doc = user_repo.get_user(clean_email)
    if not doc:
        return None

    stored_hash = doc.get("password_hash")
    if not stored_hash:
        return None

    if not verify_password(password, stored_hash):
        return None

    return User.model_validate(doc)


def _sanitize_handle(raw: str) -> str:
    """Convert an arbitrary string into a clean lowercase user handle."""
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", raw).strip("_").lower()
    return clean or f"user_{secrets.token_hex(4)}"


def register_user(
    user_repo: Any,
    email: str,
    password: str,
    display_name: str,
    user_id: Optional[str] = None,
    settings: Optional[UserSettings] = None,
) -> User:
    """Register a new user record with email, hashed password, and unique handle."""
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email:
        raise ValueError("A valid email address is required.")

    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    clean_name = (display_name or "").strip()
    if not clean_name:
        raise ValueError("Display name cannot be empty.")

    # Check if email is already registered
    existing_by_email = user_repo.get_user(clean_email)
    if existing_by_email:
        raise ValueError(f"An account with email '{clean_email}' already exists.")

    # Determine unique user_id handle
    if user_id and user_id.strip():
        handle = _sanitize_handle(user_id.strip())
        existing_by_handle = user_repo.get_user(handle)
        if existing_by_handle:
            raise ValueError(f"User handle '{handle}' is already in use.")
    else:
        base_handle = _sanitize_handle(clean_email.split("@")[0])
        handle = base_handle
        attempts = 0
        while user_repo.get_user(handle) is not None and attempts < 100:
            attempts += 1
            handle = f"{base_handle}_{secrets.token_hex(2)}"

    pw_hash = hash_password(password)
    now = utc_now()
    new_user = User(
        user_id=handle,
        email=clean_email,
        display_name=clean_name,
        password_hash=pw_hash,
        settings=settings or UserSettings(units="metric", memory_enabled=True),
        created_at=now,
        updated_at=now,
    )

    persisted_doc = user_repo.upsert_user(new_user)
    return User.model_validate(persisted_doc)


def delete_user_account(user_repo: Any, identifier: str, cascade: bool = True) -> bool:
    """Delete a user account and optionally cascade delete their memories and messages."""
    return bool(user_repo.delete_user(identifier, cascade=cascade))
