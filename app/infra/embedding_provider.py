"""Factory and lifecycle manager for vector embedding strategies."""

import logging
from typing import Any, Optional

from app.infra.providers.auto_embedding import AutoEmbeddingStrategy
from app.infra.providers.base import EmbeddingError, VectorStrategy
from app.infra.providers.mock_embedding import MockEmbeddingStrategy
from app.infra.providers.self_embedding import SelfEmbeddingStrategy

logger = logging.getLogger(__name__)

_strategy_instance: Optional[VectorStrategy] = None


def get_vector_strategy(settings: Optional[dict[str, Any]] = None) -> VectorStrategy:
    """Return the configured VectorStrategy singleton instance.

    Args:
        settings: Optional dictionary to override config settings.

    Returns:
        VectorStrategy instance matching EMBEDDING_MODE.
    """
    global _strategy_instance
    if _strategy_instance is not None and settings is None:
        return _strategy_instance

    from app.infra import config

    cfg = settings or {}
    mode = str(cfg.get("EMBEDDING_MODE", config.EMBEDDING_MODE)).strip().lower()
    model = str(cfg.get("EMBEDDING_MODEL", config.EMBEDDING_MODEL)).strip()
    dimensions = int(cfg.get("EMBEDDING_DIMENSIONS", config.EMBEDDING_DIMENSIONS))
    index_name = str(cfg.get("VECTOR_INDEX_NAME", config.VECTOR_INDEX_NAME)).strip()
    text_path = str(cfg.get("VECTOR_TEXT_PATH", config.VECTOR_TEXT_PATH)).strip()
    num_candidates = int(cfg.get("VECTOR_NUM_CANDIDATES", config.VECTOR_NUM_CANDIDATES))
    api_key = str(cfg.get("VOYAGE_API_KEY", config.VOYAGE_API_KEY)).strip()

    strategy: VectorStrategy
    if mode == "auto":
        print(
            "[INFO] Atlas Automated Embedding (auto mode) configured. "
            "Note: Automated embedding requires an Atlas M10+ dedicated cluster with Voyage AI enabled."
        )
        logger.info(
            "Atlas Automated Embedding (auto mode) requires a MongoDB Atlas M10+ cluster with Voyage AI enabled."
        )
        strategy = AutoEmbeddingStrategy(
            model_name=model,
            index_name=index_name,
            text_path=text_path,
            num_candidates=num_candidates,
        )
    elif mode == "self":
        if not api_key:
            raise EmbeddingError("VOYAGE_API_KEY is required for self embedding mode.")
        strategy = SelfEmbeddingStrategy(
            model_name=model,
            dimensions=dimensions,
            api_key=api_key,
            index_name=index_name,
            text_path=text_path,
            num_candidates=num_candidates,
        )
    elif mode == "mock":
        strategy = MockEmbeddingStrategy(
            dimensions=dimensions,
            index_name=index_name,
            text_path=text_path,
            num_candidates=num_candidates,
        )
    else:
        raise ValueError(
            f"Unsupported EMBEDDING_MODE '{mode}'. Allowed modes: 'auto', 'self', 'mock'."
        )

    if settings is None:
        _strategy_instance = strategy

    return strategy


def reset_vector_strategy() -> None:
    """Clear cached VectorStrategy instance for testing purposes."""
    global _strategy_instance
    _strategy_instance = None

