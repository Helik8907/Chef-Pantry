"""Application configuration and MongoDB connection manager."""

import os
from pathlib import Path
from typing import Optional
import urllib.parse
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

# Load environment: prioritize development configs, then .env, then .env.example
BASE_DIR = Path(__file__).resolve().parent.parent.parent
env_file = None
for candidate in [".env.development", ".env.devlopment", ".env", ".env.example"]:
    candidate_path = BASE_DIR / candidate
    if candidate_path.exists():
        env_file = candidate_path
        break
if env_file:
    load_dotenv(dotenv_path=env_file, override=True)

# MongoDB Configuration
RAW_MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "")

# Auto-substitute <db_password> placeholder if present
if "<db_password>" in RAW_MONGO_URI and MONGO_PASSWORD:
    MONGO_URI = RAW_MONGO_URI.replace("<db_password>", urllib.parse.quote_plus(MONGO_PASSWORD))
else:
    MONGO_URI = RAW_MONGO_URI

MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "chef_pantry")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("MODEL", "gemini-3.8-flash").strip()

# LLM Generation Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
LLM_TEMPERATURE_EXTRACTION = float(os.getenv("LLM_TEMPERATURE_EXTRACTION", "0.1"))
LLM_TEMPERATURE_CHEF = float(os.getenv("LLM_TEMPERATURE_CHEF", "0.7"))
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2048"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20.0"))

# Embedding & Vector Configuration
EMBEDDING_MODE = os.getenv("EMBEDDING_MODE", "mock").strip().lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3.5-lite").strip()
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "memories_vector_index").strip()
VECTOR_TEXT_PATH = os.getenv("VECTOR_TEXT_PATH", "text").strip()
VECTOR_NUM_CANDIDATES = int(os.getenv("VECTOR_NUM_CANDIDATES", "100"))
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "").strip()

def get_mongo_client(timeout_ms: int = 5000) -> MongoClient:
    """Get or create the singleton MongoDB client (delegated to db module)."""
    from app.infra import db
    return db.get_mongo_client(timeout_ms=timeout_ms)


def get_database(db_name: Optional[str] = None) -> Database:
    """Return a reference to the MongoDB database (delegated to db module)."""
    from app.infra import db
    return db.get_database(db_name=db_name)


def test_mongo_connection(timeout_ms: int = 5000) -> bool:
    """Ping MongoDB server and print success or failure notifications to the console."""
    from app.infra import db
    print("=" * 60)
    print("Connecting to MongoDB Atlas server...")
    print(f"Target Database: {MONGO_DB_NAME}")
    success = db.ping_database(timeout_ms=timeout_ms)
    if success:
        print("[SUCCESS] Connected to MongoDB server successfully!")
    else:
        print("[FAILURE] Failed to connect to MongoDB server.")
    print("=" * 60)
    return success


if __name__ == "__main__":
    test_mongo_connection()

