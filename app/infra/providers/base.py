"""Base classes, exceptions, and retry utilities for vector embedding strategies."""

from abc import ABC, abstractmethod
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class EmbeddingError(Exception):
    """Exception raised for embedding, vector generation, or vector search errors."""
    pass


def run_with_backoff(
    callable_fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 0.5,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Execute a callable with exponential backoff on retryable exceptions."""
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return callable_fn()
        except retryable_exceptions as err:
            last_err = err
            if attempt == max_attempts - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    if last_err is not None:
        raise last_err
    raise RuntimeError("run_with_backoff completed without returning or raising.")


class VectorStrategy(ABC):
    """Abstract base class for vector embedding and Atlas vectorSearch strategies."""

    def __init__(
        self,
        index_name: str = "memories_vector_index",
        text_path: str = "text",
        num_candidates: int = 100,
    ) -> None:
        self.index_name = index_name
        self.text_path = text_path
        self.num_candidates = num_candidates

    @property
    @abstractmethod
    def mode(self) -> str:
        """Strategy mode identifier: 'auto', 'self', or 'mock'."""
        pass

    @abstractmethod
    def prepare_document(self, memory_dict: dict[str, Any]) -> dict[str, Any]:
        """Prepare a document dict before inserting into the database."""
        pass

    @abstractmethod
    def build_index_definition(self, filter_paths: list[str]) -> dict[str, Any]:
        """Build the MongoDB Atlas vectorSearch index definition dictionary."""
        pass

    def build_vector_search_stage(
        self,
        query_text: str,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        num_candidates: int | None = None,
    ) -> dict[str, Any]:
        """Build the full $vectorSearch aggregation stage dictionary."""
        effective_num_candidates = (
            num_candidates if num_candidates is not None else self.num_candidates
        )
        vector_search: dict[str, Any] = {
            "index": self.index_name,
            "limit": limit,
            "numCandidates": effective_num_candidates,
        }

        if self.mode == "auto":
            vector_search["path"] = self.text_path
            vector_search["query"] = query_text
        else:
            vector_search["path"] = "embedding"
            vector_search["queryVector"] = self.embed_query(query_text)

        if filters:
            filter_clause: dict[str, Any] = {}
            for key, val in filters.items():
                if val is None:
                    continue
                if isinstance(val, (list, tuple, set)):
                    filter_clause[key] = {"$in": list(val)}
                else:
                    filter_clause[key] = val
            if filter_clause:
                vector_search["filter"] = filter_clause

        return {"$vectorSearch": vector_search}

    @abstractmethod
    def embed_query(self, text: str) -> list[float] | None:
        """Embed a query string into a vector, or return None in auto mode."""
        pass

