"""Self-managed vector embedding strategy using the Voyage AI client."""

from typing import Any, Optional

from app.infra.providers.base import EmbeddingError, VectorStrategy, run_with_backoff


class SelfEmbeddingStrategy(VectorStrategy):
    """Generates and manages vectors client-side via Voyage AI API."""

    def __init__(
        self,
        model_name: str | None = None,
        dimensions: int | None = None,
        api_key: str | None = None,
        index_name: str | None = None,
        text_path: str | None = None,
        num_candidates: int | None = None,
        batch_size: int = 128,
    ) -> None:
        from app.infra.config import (
            EMBEDDING_DIMENSIONS,
            EMBEDDING_MODEL,
            VECTOR_INDEX_NAME,
            VECTOR_NUM_CANDIDATES,
            VECTOR_TEXT_PATH,
            VOYAGE_API_KEY,
        )

        self.model_name = (model_name or EMBEDDING_MODEL).strip()
        self.dimensions = dimensions if dimensions is not None else EMBEDDING_DIMENSIONS
        self.api_key = (api_key if api_key is not None else VOYAGE_API_KEY).strip()
        self.batch_size = max(1, batch_size)
        self._client: Optional[Any] = None

        if not self.api_key:
            raise EmbeddingError("VOYAGE_API_KEY is required for self embedding mode.")

        super().__init__(
            index_name=index_name or VECTOR_INDEX_NAME,
            text_path=text_path or VECTOR_TEXT_PATH,
            num_candidates=num_candidates or VECTOR_NUM_CANDIDATES,
        )

    @property
    def mode(self) -> str:
        """Return 'self' mode."""
        return "self"

    def _get_client(self) -> Any:
        """Lazily import and initialize the Voyage AI client."""
        if self._client is None:
            try:
                import voyageai  # type: ignore[import-not-found]
            except ImportError as err:
                raise EmbeddingError(
                    "The 'voyageai' package is required for self embedding mode. "
                    "Please install it before using self embedding."
                ) from err
            self._client = voyageai.Client(api_key=self.api_key)
        return self._client

    def _embed_batch(self, batch: list[str], input_type: str) -> list[list[float]]:
        """Embed a single batch of texts with retry and backoff."""
        client = self._get_client()

        def _call() -> list[list[float]]:
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "input_type": input_type,
            }
            if self.dimensions:
                kwargs["output_dimension"] = self.dimensions
            try:
                res = client.embed(batch, **kwargs)
            except TypeError:
                kwargs.pop("output_dimension", None)
                res = client.embed(batch, **kwargs)
            return res.embeddings

        try:
            embeddings = run_with_backoff(_call, max_attempts=3, base_delay=0.5)
        except Exception as err:
            raise EmbeddingError(f"Voyage AI embedding request failed: {err}") from err

        for vec in embeddings:
            if len(vec) != self.dimensions:
                raise EmbeddingError(
                    f"Vector dimension mismatch: expected {self.dimensions}, got {len(vec)}"
                )
        return embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of documents in batches using 'document' input type."""
        if not texts:
            return []
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            all_embeddings.extend(self._embed_batch(batch, input_type="document"))
        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query using 'query' input type."""
        embeddings = self._embed_batch([text], input_type="query")
        return embeddings[0]

    def prepare_document(self, memory_dict: dict[str, Any]) -> dict[str, Any]:
        """Attach embedding vector computed from document text."""
        doc = dict(memory_dict)
        text_val = str(doc.get(self.text_path) or doc.get("text") or "")
        embeddings = self.embed_documents([text_val])
        doc["embedding"] = embeddings[0] if embeddings else [0.0] * self.dimensions
        return doc

    def build_index_definition(self, filter_paths: list[str]) -> dict[str, Any]:
        """Build Atlas vectorSearch index definition for self-managed embedding."""
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

