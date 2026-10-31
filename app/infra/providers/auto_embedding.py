"""Atlas Automated Embedding strategy."""

from typing import Any

from app.infra.providers.base import VectorStrategy


class AutoEmbeddingStrategy(VectorStrategy):
    """Atlas Automated Embedding strategy where Atlas manages document and query vectors."""

    ALLOWED_MODELS = {"voyage-3-large", "voyage-3.5", "voyage-3.5-lite"}

    def __init__(
        self,
        model_name: str | None = None,
        index_name: str | None = None,
        text_path: str | None = None,
        num_candidates: int | None = None,
    ) -> None:
        from app.infra.config import (
            EMBEDDING_MODEL,
            VECTOR_INDEX_NAME,
            VECTOR_TEXT_PATH,
            VECTOR_NUM_CANDIDATES,
        )

        selected_model = (model_name or EMBEDDING_MODEL).strip()
        if selected_model not in self.ALLOWED_MODELS:
            raise ValueError(
                f"Unsupported Voyage model '{selected_model}' for auto embedding. "
                f"Allowed models: {sorted(self.ALLOWED_MODELS)}"
            )

        self.model_name = selected_model
        super().__init__(
            index_name=index_name or VECTOR_INDEX_NAME,
            text_path=text_path or VECTOR_TEXT_PATH,
            num_candidates=num_candidates or VECTOR_NUM_CANDIDATES,
        )

    @property
    def mode(self) -> str:
        """Return 'auto' mode."""
        return "auto"

    def prepare_document(self, memory_dict: dict[str, Any]) -> dict[str, Any]:
        """Return memory document unchanged without adding an embedding field."""
        doc = dict(memory_dict)
        doc.pop("embedding", None)
        return doc

    def build_index_definition(self, filter_paths: list[str]) -> dict[str, Any]:
        """Build Atlas vectorSearch index definition for automated embedding."""
        fields: list[dict[str, Any]] = [
            {"type": "text", "path": self.text_path, "model": self.model_name}
        ]
        for path in filter_paths:
            fields.append({"type": "filter", "path": path})
        return {"fields": fields}

    def embed_query(self, text: str) -> list[float] | None:
        """In auto mode, query embedding is performed by Atlas server-side."""
        return None

