"""Domain models and data schemas for Memory Chef.

Pure Python data models implemented with Pydantic v2.
No I/O, database, network, Streamlit, or LLM logic.
"""

from datetime import datetime, timezone
from enum import Enum
import secrets
from typing import Any, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ============================================================================
# ENUMS
# ============================================================================

class MemoryType(str, Enum):
    """Classification of culinary memories."""
    ALLERGY = "allergy"
    PREFERENCE = "preference"
    MEAL_OUTCOME = "meal_outcome"
    PANTRY = "pantry"
    TEMPORARY_CONTEXT = "temporary_context"


class MemoryStatus(str, Enum):
    """Lifecycle status of stored memories."""
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class MemorySource(str, Enum):
    """Source origin of a memory."""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Visibility(str, Enum):
    """Privacy and accessibility scope."""
    PRIVATE = "private"
    SHARED = "shared"


class MessageRole(str, Enum):
    """Role associated with a conversational turn."""
    USER = "user"
    ASSISTANT = "assistant"


# ============================================================================
# HELPERS
# ============================================================================

def utc_now() -> datetime:
    """Return the current datetime in timezone-aware UTC."""
    return datetime.now(timezone.utc)


def generate_object_id() -> str:
    """Generate a random 24-character hexadecimal string compatible with MongoDB ObjectId."""
    return secrets.token_hex(12)


def is_valid_object_id(oid: str) -> bool:
    """Check whether a string is a valid 24-character hexadecimal ObjectId."""
    if not isinstance(oid, str) or len(oid) != 24:
        return False
    try:
        int(oid, 16)
        return True
    except ValueError:
        return False


def to_object_id_str(val: Any) -> str:
    """Convert an ObjectId-like instance or string to a string representation."""
    return str(val)


def from_object_id_str(val: str) -> str:
    """Validate and return the string representation of an ObjectId."""
    if not is_valid_object_id(val):
        raise ValueError(f"'{val}' is not a valid 24-character hexadecimal ObjectId.")
    return val


def ensure_timezone_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure that a datetime is timezone-aware. Rejects naive datetimes."""
    if dt is not None and (dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None):
        raise ValueError("Datetime must be timezone-aware (e.g., UTC).")
    return dt


# ============================================================================
# BASE MODELS
# ============================================================================

class MongoBaseModel(BaseModel):
    """Base domain model configured for MongoDB alias and field population."""
    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
    )


# ============================================================================
# USER MODELS
# ============================================================================

class UserSettings(BaseModel):
    """User preferences for measurement units and memory retention."""
    model_config = ConfigDict(populate_by_name=True)

    units: str = Field(default="metric", description="Preferred measurement system ('metric' or 'imperial').")
    memory_enabled: bool = Field(default=True, description="Whether memory retention is active.")


class User(MongoBaseModel):
    """User profile record with unique handle and configuration settings."""
    id: str = Field(default_factory=generate_object_id, alias="_id", description="MongoDB ObjectId string.")
    user_id: str = Field(..., description="Unique user handle.")
    display_name: str = Field(..., description="Human-readable user display name.")
    created_at: datetime = Field(default_factory=utc_now, description="Account creation timestamp in UTC.")
    settings: UserSettings = Field(default_factory=UserSettings, description="User specific settings.")

    @field_validator("created_at")
    @classmethod
    def validate_user_created_at(cls, v: datetime) -> datetime:
        return ensure_timezone_aware(v)


# ============================================================================
# STRUCTURED PAYLOAD HELPERS
# ============================================================================

class AllergyData(BaseModel):
    """Structured payload helper for allergy memories."""
    model_config = ConfigDict(populate_by_name=True)

    allergen: str = Field(..., description="Name of the allergen.")
    severity: Optional[str] = Field(default=None, description="Severity description (e.g. mild, severe).")


class PreferenceData(BaseModel):
    """Structured payload helper for culinary preferences."""
    model_config = ConfigDict(populate_by_name=True)

    kind: str = Field(..., description="Preference kind: 'like', 'dislike', or 'diet'.")
    item: str = Field(..., description="Target item, ingredient, or culinary concept.")

    @field_validator("kind")
    @classmethod
    def validate_preference_kind(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in {"like", "dislike", "diet"}:
            raise ValueError("Preference kind must be 'like', 'dislike', or 'diet'.")
        return cleaned


class MealOutcomeData(BaseModel):
    """Structured payload helper for recorded meal outcomes."""
    model_config = ConfigDict(populate_by_name=True)

    dish: str = Field(..., description="Name or description of the prepared dish.")
    rating: Optional[int] = Field(default=None, ge=1, le=5, description="Dish rating from 1 to 5.")
    feedback: Optional[str] = Field(default=None, description="Free-text meal feedback or critique.")


class PantryData(BaseModel):
    """Structured payload helper for pantry inventory items."""
    model_config = ConfigDict(populate_by_name=True)

    item: str = Field(..., description="Name of pantry ingredient or item.")
    quantity: Optional[str] = Field(default=None, description="Quantity or inventory amount string.")


class TemporaryContextData(BaseModel):
    """Structured payload helper for temporary situational context."""
    model_config = ConfigDict(populate_by_name=True)

    context: str = Field(..., description="Context description (e.g. dinner party, quick lunch).")
    for_people: Optional[int] = Field(default=None, ge=1, description="Number of people being served.")


# ============================================================================
# CORE MEMORY MODEL
# ============================================================================

class Memory(MongoBaseModel):
    """Core memory item storing user profile, preferences, allergies, or context."""

    # Identity
    id: str = Field(default_factory=generate_object_id, alias="_id", description="MongoDB ObjectId string.")
    user_id: str = Field(..., description="ID of the user who owns this memory.")
    session_id: Optional[str] = Field(default=None, description="Session ID during which memory was captured.")
    type: MemoryType = Field(..., description="Categorical type of memory.")

    # Content
    text: str = Field(..., description="Human-readable memory text statement.")
    structured: dict[str, Any] = Field(default_factory=dict, description="Structured payload metadata.")
    tags: list[str] = Field(default_factory=list, description="Normalized classification tags.")
    source: MemorySource = Field(default=MemorySource.USER, description="Source origin of the memory.")
    source_message_id: Optional[str] = Field(default=None, description="Referenced message ID if captured from chat.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score.")
    embedding: Optional[list[float]] = Field(default=None, exclude=True, description="Dense vector embedding.")

    # Time
    created_at: datetime = Field(default_factory=utc_now, description="Memory creation timestamp in UTC.")
    updated_at: datetime = Field(default_factory=utc_now, description="Last update timestamp in UTC.")
    last_used_at: Optional[datetime] = Field(default=None, description="Timestamp of when memory was recalled.")
    expires_at: Optional[datetime] = Field(default=None, description="Expiration timestamp in UTC.")

    # Lifecycle
    status: MemoryStatus = Field(default=MemoryStatus.ACTIVE, description="Lifecycle status.")
    superseded_by: Optional[str] = Field(default=None, description="ID of memory that superseded this one.")
    supersedes: Optional[str] = Field(default=None, description="ID of memory that this one supersedes.")
    protected: bool = Field(default=False, description="Whether memory is protected from eviction.")
    use_count: int = Field(default=0, ge=0, description="Number of times recalled in generation.")
    deleted_at: Optional[datetime] = Field(default=None, description="Timestamp when soft-deleted.")

    # Privacy
    visibility: Visibility = Field(default=Visibility.PRIVATE, description="Memory sharing visibility.")

    @field_validator("text", mode="before")
    @classmethod
    def validate_text(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("Text must be a string.")
        stripped = v.strip()
        if not stripped:
            raise ValueError("Text must not be empty.")
        return stripped

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: Any) -> list[str]:
        if v is None:
            return []
        cleaned_tags: list[str] = []
        seen = set()
        for tag in v:
            if isinstance(tag, str):
                normalized = tag.strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    cleaned_tags.append(normalized)
        return cleaned_tags

    @field_validator("created_at", "updated_at", "last_used_at", "expires_at", "deleted_at")
    @classmethod
    def validate_datetimes(cls, v: Optional[datetime]) -> Optional[datetime]:
        return ensure_timezone_aware(v)

    @model_validator(mode="after")
    def apply_lifecycle_and_allergy_rules(self) -> "Memory":
        if self.type == MemoryType.ALLERGY:
            self.protected = True
            self.expires_at = None

        if self.status == MemoryStatus.SUPERSEDED and not self.superseded_by:
            raise ValueError("When status is 'superseded', 'superseded_by' must be provided.")

        return self

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Check if memory has expired relative to `now` (default: utc_now())."""
        if self.expires_at is None:
            return False
        ref = now if now is not None else utc_now()
        if ref.tzinfo is None or ref.tzinfo.utcoffset(ref) is None:
            raise ValueError("Reference datetime 'now' must be timezone-aware.")
        return ref >= self.expires_at

    def is_active(self, now: Optional[datetime] = None) -> bool:
        """Check if memory is active and not expired."""
        return self.status == MemoryStatus.ACTIVE and not self.is_expired(now)


# ============================================================================
# EXTRACTION & RETRIEVAL MODELS
# ============================================================================

class CandidateMemory(BaseModel):
    """Extracted memory draft returned by the LLM extraction step before storing."""
    model_config = ConfigDict(populate_by_name=True)

    type: MemoryType = Field(..., description="Proposed memory type.")
    text: str = Field(..., description="Proposed memory text statement.")
    structured: dict[str, Any] = Field(default_factory=dict, description="Extracted structured metadata.")
    tags: list[str] = Field(default_factory=list, description="Categorization tags.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score.")
    is_temporary: bool = Field(default=False, description="Whether memory is short-lived context.")
    suggested_ttl_hours: Optional[int] = Field(default=None, ge=1, description="Suggested time-to-live in hours.")
    is_correction_of_text: Optional[str] = Field(default=None, description="Text of earlier memory being contradicted.")

    @field_validator("text", mode="before")
    @classmethod
    def validate_candidate_text(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("Candidate text must be a string.")
        stripped = v.strip()
        if not stripped:
            raise ValueError("Candidate text must not be empty.")
        return stripped

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_candidate_tags(cls, v: Any) -> list[str]:
        if v is None:
            return []
        cleaned_tags: list[str] = []
        seen = set()
        for tag in v:
            if isinstance(tag, str):
                normalized = tag.strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    cleaned_tags.append(normalized)
        return cleaned_tags


class ExtractionResult(BaseModel):
    """Container for candidate memories extracted from a conversation."""
    model_config = ConfigDict(populate_by_name=True)

    candidates: list[CandidateMemory] = Field(default_factory=list, description="Extracted candidate memories.")


class MemoryUsed(BaseModel):
    """Summary of a recalled memory used in generating an assistant response."""
    model_config = ConfigDict(populate_by_name=True)

    memory_id: str = Field(..., description="ID of recalled memory.")
    text: str = Field(..., description="Content of recalled memory.")
    type: MemoryType = Field(..., description="Type classification of memory.")
    score: float = Field(..., description="Relevance and ranking score.")
    reasons: list[str] = Field(default_factory=list, description="Explanation for inclusion.")


class ScoreBreakdown(BaseModel):
    """Individual score factors contributing to memory ranking."""
    model_config = ConfigDict(populate_by_name=True)

    similarity: float = Field(default=0.0, description="Vector/semantic similarity score.")
    recency: float = Field(default=0.0, description="Recency decay score.")
    rating_boost: float = Field(default=0.0, description="Rating or explicit feedback boost.")
    type_priority: float = Field(default=0.0, description="Priority weight based on memory type.")
    final_score: float = Field(default=0.0, description="Composite final ranking score.")


class RecalledMemory(BaseModel):
    """Memory item recalled during retrieval with score attribution."""
    model_config = ConfigDict(populate_by_name=True)

    memory: Memory = Field(..., description="Core memory record.")
    score: ScoreBreakdown = Field(..., description="Breakdown of retrieval score.")
    reasons: list[str] = Field(default_factory=list, description="Reasoning behind ranking and selection.")
    matched_filters: dict[str, Any] = Field(default_factory=dict, description="Metadata filters matched during retrieval.")


# ============================================================================
# CHAT & MESSAGE MODELS
# ============================================================================

class Message(MongoBaseModel):
    """Conversation message with linked memory attribution."""
    id: str = Field(default_factory=generate_object_id, alias="_id", description="MongoDB ObjectId string.")
    user_id: str = Field(..., description="User ID associated with the message.")
    session_id: str = Field(..., description="Session identifier.")
    role: MessageRole = Field(..., description="Role of the author ('user' or 'assistant').")
    content: str = Field(..., description="Message text content.")
    memories_used: list[MemoryUsed] = Field(default_factory=list, description="Memories referenced in response.")
    memories_created: list[str] = Field(default_factory=list, description="Memory IDs created from this turn.")
    created_at: datetime = Field(default_factory=utc_now, description="Message creation timestamp in UTC.")

    @field_validator("created_at")
    @classmethod
    def validate_message_created_at(cls, v: datetime) -> datetime:
        return ensure_timezone_aware(v)


class ChatRequest(BaseModel):
    """Incoming user request for chat interaction."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(..., description="Unique user identifier.")
    session_id: str = Field(..., description="Active session identifier.")
    message: str = Field(..., description="User message text.")


class ChatResponse(BaseModel):
    """Outgoing response payload from the chef assistant."""
    model_config = ConfigDict(populate_by_name=True)

    answer: str = Field(..., description="Synthesized assistant response.")
    memories_used: list[MemoryUsed] = Field(default_factory=list, description="Memories retrieved and utilized.")
    memories_created: list[Memory] = Field(default_factory=list, description="Newly extracted and persisted memories.")
    memories_superseded: list[str] = Field(default_factory=list, description="IDs of memories that were superseded.")
    safety_warnings: list[str] = Field(default_factory=list, description="Safety or allergy warning notices.")
    pending_confirmations: list[Any] = Field(default_factory=list, description="Pending changes requiring user confirmation.")
    ambiguous_corrections: list[Any] = Field(default_factory=list, description="Ambiguous corrections detected.")
    warnings: list[str] = Field(default_factory=list, description="Execution and system warnings.")
    trace: Optional["TraceInfo"] = Field(default=None, description="Detailed execution trace information.")
    message_id: Optional[str] = Field(default=None, description="Persisted assistant message ID.")


class MemoryUpdateRequest(BaseModel):
    """Payload for updating or correcting an existing memory from the inspector."""
    model_config = ConfigDict(populate_by_name=True)

    text: Optional[str] = Field(default=None, description="Updated text content.")
    structured: Optional[dict[str, Any]] = Field(default=None, description="Updated structured payload.")
    tags: Optional[list[str]] = Field(default=None, description="Updated tags.")
    expires_at: Optional[datetime] = Field(default=None, description="Updated expiration timestamp in UTC.")

    @field_validator("text", mode="before")
    @classmethod
    def validate_update_text(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("Text must be a string.")
        stripped = v.strip()
        if not stripped:
            raise ValueError("Text cannot be empty or whitespace only.")
        return stripped

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_update_tags(cls, v: Any) -> Optional[list[str]]:
        if v is None:
            return None
        cleaned_tags: list[str] = []
        seen = set()
        for tag in v:
            if isinstance(tag, str):
                normalized = tag.strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    cleaned_tags.append(normalized)
        return cleaned_tags

    @field_validator("expires_at")
    @classmethod
    def validate_update_expires_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        return ensure_timezone_aware(v)


# ============================================================================
# ORCHESTRATION & TRACE MODELS
# ============================================================================

class StepTiming(BaseModel):
    """Execution timing for an individual orchestration step."""
    model_config = ConfigDict(populate_by_name=True)

    step: str = Field(..., description="Name of the orchestration step.")
    ms: float = Field(..., description="Elapsed execution time in milliseconds.")


class TraceInfo(BaseModel):
    """Detailed execution trace information for a chat turn."""
    model_config = ConfigDict(populate_by_name=True)

    extracted: list[CandidateMemory] = Field(default_factory=list, description="Extracted candidate memories.")
    stored_ids: list[str] = Field(default_factory=list, description="IDs of newly stored memories.")
    superseded: list[str] = Field(default_factory=list, description="IDs of superseded memories.")
    duplicates_refreshed: list[str] = Field(default_factory=list, description="IDs of refreshed duplicate memories.")
    skipped: list[dict[str, Any]] = Field(default_factory=list, description="Skipped candidates with reason and summary.")
    recalled_count: int = Field(default=0, ge=0, description="Number of memories recalled.")
    always_applied_ids: list[str] = Field(default_factory=list, description="IDs of always-applied memories.")
    timings: list[StepTiming] = Field(default_factory=list, description="Timings of individual steps.")
    degraded_steps: list[str] = Field(default_factory=list, description="Steps that failed and degraded gracefully.")


ChatResponse.model_rebuild()


