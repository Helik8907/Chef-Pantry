"""MongoDB database connector and client connection lifecycle management."""

import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.infra import config

logger = logging.getLogger(__name__)

_mongo_client: Optional[MongoClient] = None


def get_mongo_client(
    uri: Optional[str] = None,
    timeout_ms: int = 5000,
) -> MongoClient:
    """Retrieve or initialize the singleton MongoDB client."""
    global _mongo_client
    if _mongo_client is None:
        effective_uri = uri or config.MONGO_URI
        if not effective_uri:
            raise ValueError("MongoDB URI is not configured in environment or settings.")
        logger.info("Initializing MongoDB client connection.")
        _mongo_client = MongoClient(
            effective_uri,
            serverSelectionTimeoutMS=timeout_ms,
            tz_aware=True,
        )
    return _mongo_client


def get_database(
    db_name: Optional[str] = None,
    client: Optional[MongoClient] = None,
) -> Database:
    """Retrieve a reference to the target MongoDB database."""
    effective_client = client or get_mongo_client()
    effective_db_name = db_name or config.MONGO_DB_NAME
    return effective_client[effective_db_name]


def close_mongo_client() -> None:
    """Close the active MongoDB client connection if open."""
    global _mongo_client
    if _mongo_client is not None:
        try:
            _mongo_client.close()
            logger.info("MongoDB client connection closed.")
        finally:
            _mongo_client = None


def ping_database(timeout_ms: int = 5000) -> bool:
    """Execute a ping command against MongoDB admin database to verify connectivity."""
    try:
        client = get_mongo_client(timeout_ms=timeout_ms)
        client.admin.command("ping")
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError) as err:
        logger.error("Failed to connect to MongoDB server: %s", err)
        return False
    except Exception as err:
        logger.error("Unexpected error connecting to MongoDB: %s", err)
        return False

