"""User repository for MongoDB persistence and user lifecycle management."""

import logging
from typing import Any, Optional
from bson import ObjectId
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.infra.repositories.base import ensure_utc_datetimes

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository handling MongoDB persistence and profile management for users."""

    def __init__(self, db: Database) -> None:
        """Initialize repository with injected database handle."""
        self.db = db

    def get_user(self, identifier: str) -> Optional[dict[str, Any]]:
        """Retrieve user document by unique user_id handle, email, or MongoDB _id."""
        clean_id = str(identifier).strip()
        conditions: list[dict[str, Any]] = [
            {"user_id": clean_id},
            {"_id": clean_id},
            {"email": clean_id.lower()},
        ]
        if ObjectId.is_valid(clean_id):
            conditions.append({"_id": ObjectId(clean_id)})

        doc = self.db.users.find_one({"$or": conditions})
        if doc:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            ensure_utc_datetimes(doc, fields=("created_at", "updated_at"))
        return doc

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        """Retrieve user document by email address."""
        if not email:
            return None
        return self.get_user(email.strip().lower())

    def upsert_user(self, user: Any) -> dict[str, Any]:
        """Upsert user profile document by user_id and return persisted record."""
        if hasattr(user, "model_dump"):
            doc = user.model_dump(by_alias=True)
            if hasattr(user, "password_hash") and user.password_hash is not None:
                doc["password_hash"] = user.password_hash
        else:
            doc = dict(user)

        user_id = doc.get("user_id")
        if not user_id:
            raise ValueError("User document must contain 'user_id'.")

        if doc.get("email"):
            doc["email"] = str(doc["email"]).strip().lower()

        try:
            self.db.users.update_one(
                {"user_id": user_id},
                {"$set": doc},
                upsert=True,
            )
        except DuplicateKeyError as err:
            err_str = str(err)
            if "email" in err_str:
                raise ValueError(f"An account with email '{doc.get('email')}' already exists.") from err
            if "user_id" in err_str:
                raise ValueError(f"User handle '{user_id}' already exists.") from err
            raise ValueError(f"Duplicate user record constraint violation: {err_str}") from err

        persisted = self.get_user(user_id)
        return persisted if persisted is not None else doc

    def delete_user(self, identifier: str, cascade: bool = True) -> bool:
        """Permanently remove a user record and optionally cascade delete their memories and messages."""
        doc = self.get_user(identifier)
        if not doc:
            return False

        target_id = doc.get("_id")
        actual_user_id = doc.get("user_id") or identifier

        delete_query: dict[str, Any] = {"$or": [{"_id": target_id}]}
        if ObjectId.is_valid(str(target_id)):
            delete_query["$or"].append({"_id": ObjectId(str(target_id))})
        if actual_user_id:
            delete_query["$or"].append({"user_id": actual_user_id})

        res = self.db.users.delete_one(delete_query)
        deleted = res.deleted_count > 0

        if deleted and cascade and actual_user_id:
            memories_res = self.db.memories.delete_many({"user_id": actual_user_id})
            messages_res = self.db.messages.delete_many({"user_id": actual_user_id})
            logger.info(
                "Cascade deleted %d memories and %d messages for user_id=%s",
                memories_res.deleted_count,
                messages_res.deleted_count,
                actual_user_id,
            )
        return deleted
