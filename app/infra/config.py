"""Application configuration and MongoDB connection manager."""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

# Load .env first; fallback to .env.example
BASE_DIR = Path(__file__).resolve().parent.parent.parent
env_file = BASE_DIR / ".env"
if not env_file.exists():
    env_file = BASE_DIR / ".env.example"
load_dotenv(dotenv_path=env_file)

# MongoDB Configuration
RAW_MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "")

# Auto-substitute <db_password> placeholder if present
if "<db_password>" in RAW_MONGO_URI and MONGO_PASSWORD:
    MONGO_URI = RAW_MONGO_URI.replace("<db_password>", MONGO_PASSWORD)
else:
    MONGO_URI = RAW_MONGO_URI

MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "chef_pantry")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = os.getenv("MODEL", "gemini-flash-latest")

# LLM Generation Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
GEMINI_MODEL_EXTRACTION = os.getenv("GEMINI_MODEL_EXTRACTION", "gemini-2.5-flash").strip()
GEMINI_MODEL_CHEF = os.getenv("GEMINI_MODEL_CHEF", "gemini-2.5-flash").strip()
LLM_TEMPERATURE_EXTRACTION = float(os.getenv("LLM_TEMPERATURE_EXTRACTION", "0.1"))
LLM_TEMPERATURE_CHEF = float(os.getenv("LLM_TEMPERATURE_CHEF", "0.7"))
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2048"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30.0"))

# Embedding & Vector Configuration
EMBEDDING_MODE = os.getenv("EMBEDDING_MODE", "mock").strip().lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3.5-lite").strip()
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "memories_vector_index").strip()
VECTOR_TEXT_PATH = os.getenv("VECTOR_TEXT_PATH", "text").strip()
VECTOR_NUM_CANDIDATES = int(os.getenv("VECTOR_NUM_CANDIDATES", "100"))
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "").strip()

_mongo_client: Optional[MongoClient] = None


def get_mongo_client(timeout_ms: int = 5000) -> MongoClient:
    """Get or create the singleton MongoDB client."""
    global _mongo_client
    if _mongo_client is None:
        if not MONGO_URI:
            raise ValueError("MONGO_URI is not configured in the environment.")
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=timeout_ms)
    return _mongo_client


def get_database(db_name: Optional[str] = None) -> Database:
    """Return a reference to the MongoDB database."""
    client = get_mongo_client()
    return client[db_name or MONGO_DB_NAME]


def test_mongo_connection(timeout_ms: int = 5000) -> bool:
    """Ping MongoDB server and print success or failure notifications to the console."""
    print("=" * 60)
    print("Connecting to MongoDB Atlas server...")
    print(f"Target Database: {MONGO_DB_NAME}")
    try:
        client = get_mongo_client(timeout_ms=timeout_ms)
        # Execute ping command against the admin database
        client.admin.command("ping")
        print("[SUCCESS] Connected to MongoDB server successfully!")
        print("=" * 60)
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError) as err:
        print(f"[FAILURE] Failed to connect to MongoDB server: {err}")
        print("=" * 60)
        return False
    except Exception as err:
        print(f"[FAILURE] Unexpected error while connecting to MongoDB: {err}")
        print("=" * 60)
        return False


if __name__ == "__main__":
    test_mongo_connection()

