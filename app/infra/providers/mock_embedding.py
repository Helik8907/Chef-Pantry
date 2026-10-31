"""Deterministic mock embedding strategy for testing and offline development."""

import hashlib
import math
import re
from typing import Any

from app.infra.providers.base import VectorStrategy


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate the cosine similarity between two float vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class MockEmbeddingStrategy(VectorStrategy):
    """Deterministic local mock embedding strategy with no external network calls."""

    def __init__(
        self,
        dimensions: int = 256,
        index_name: str | None = None,
        text_path: str | None = None,
        num_candidates: int | None = None,
    ) -> None:
        from app.infra.config import (
            VECTOR_INDEX_NAME,
            VECTOR_TEXT_PATH,
            VECTOR_NUM_CANDIDATES,
        )

        self.dimensions = dimensions
        super().__init__(
            index_name=index_name or VECTOR_INDEX_NAME,
            text_path=text_path or VECTOR_TEXT_PATH,
            num_candidates=num_candidates or VECTOR_NUM_CANDIDATES,
        )

    @property
    def mode(self) -> str:
        """Return 'mock' mode."""
        return "mock"

    def _hash_token(self, token: str) -> int:
        """Hash a token to a bucket index deterministically."""
        digest = hashlib.md5(token.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") % self.dimensions

    def embed_query(self, text: str) -> list[float]:
        """Convert text into a deterministic, L2-normalized vector."""
        vec = [0.0] * self.dimensions
        tokens = re.findall(r"\w+", text.lower())

        if not tokens:
            val = 1.0 / math.sqrt(self.dimensions)
            return [val] * self.dimensions

        for token in tokens:
            bucket = self._hash_token(token)
            vec[bucket] += 1.0

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            return [x / norm for x in vec]
        val = 1.0 / math.sqrt(self.dimensions)
        return [val] * self.dimensions

    def prepare_document(self, memory_dict: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of the memory document with the computed embedding attached."""
        doc = dict(memory_dict)
        text_val = str(doc.get(self.text_path) or doc.get("text") or "")
        doc["embedding"] = self.embed_query(text_val)
        return doc

    def build_index_definition(self, filter_paths: list[str]) -> dict[str, Any]:
        """Build Atlas vectorSearch index definition for mock/self vector search."""
        fields: list[dict[str, Any]] = [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": self.dimensions,
                "similarity": "cosine",
            }
        ]
        for path in filter_paths:
            fields.append({"type": "filter", "path": path})
        return {"fields": fields}

