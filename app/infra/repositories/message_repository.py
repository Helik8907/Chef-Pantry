"""Message repository for MongoDB chat history and session persistence."""

import logging
from typing import Any
import pymongo
from pymongo.database import Database

from app.infra.repositories.base import ensure_utc_datetimes

logger = logging.getLogger(__name__)


class MessageRepository:
    """Repository handling persistence and aggregation for chat turns and sessions."""

    def __init__(self, db: Database) -> None:
        """Initialize repository with injected database handle."""
        self.db = db

    def insert_message(self, message: Any) -> str:
        """Persist a chat message record and return its ID string."""
        if hasattr(message, "model_dump"):
            doc = message.model_dump(by_alias=True)
        else:
            doc = dict(message)

        if "_id" not in doc and "id" in doc:
            doc["_id"] = doc.pop("id")

        res = self.db.messages.insert_one(doc)
        return str(res.inserted_id or doc.get("_id"))

    def list_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent session messages ordered from oldest to newest."""
        query = {"user_id": user_id, "session_id": session_id}
        cursor = self.db.messages.find(query).sort("created_at", pymongo.ASCENDING).limit(limit)
        results = list(cursor)
        for doc in results:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            ensure_utc_datetimes(doc, fields=("created_at",))
        return results

    def list_sessions(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List distinct user chat sessions with first/last message times and total count."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$group": {
                    "_id": "$session_id",
                    "first_message_time": {"$min": "$created_at"},
                    "last_message_time": {"$max": "$created_at"},
                    "message_count": {"$sum": 1},
                }
            },
            {"$sort": {"last_message_time": pymongo.DESCENDING}},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 0,
                    "session_id": "$_id",
                    "first_message_time": 1,
                    "last_message_time": 1,
                    "message_count": 1,
                }
            },
        ]
        results = list(self.db.messages.aggregate(pipeline))
        for doc in results:
            ensure_utc_datetimes(doc, fields=("first_message_time", "last_message_time"))
        return results

    def delete_session(self, user_id: str, session_id: str) -> int:
        """Permanently delete all messages in a session for a user and return deleted count."""
        res = self.db.messages.delete_many({"user_id": user_id, "session_id": session_id})
        return int(res.deleted_count)

