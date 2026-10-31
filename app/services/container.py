"""Dependency wiring and composition root for Memory Chef services."""

from dataclasses import dataclass
import logging
from typing import Any, Optional

from app.domain.models import utc_now
from app.domain.ranker import make_reranker
from app.infra import config
from app.infra.embedding_provider import get_vector_strategy
from app.infra.llm_client import LLMProvider, get_llm_provider
from app.infra.memory_repository import MemoryRepository
from app.infra.providers.base import VectorStrategy
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.chef import Chef
from app.services.extraction import MemoryExtractor
from app.services.memory_recall import MemoryRecall

logger = logging.getLogger(__name__)


def _get_setting(settings: Any, key: str, default: Any) -> Any:
    """Retrieve setting value from dict, object, or fallback config."""
    if settings is not None:
        if isinstance(settings, dict) and key in settings:
            return settings[key]
        if hasattr(settings, key):
            return getattr(settings, key)
    return getattr(config, key, default)


@dataclass
class Container:
    """Dependency injection container holding wired services and infrastructure singletons."""

    settings: Any
    db: Any
    repository: MemoryRepository
    vector_strategy: VectorStrategy
    llm_provider: LLMProvider
    extractor: Any
    store: Any
    lifecycle: Any
    recall: Any
    chef: Any
    orchestrator: ChatOrchestrator


def build_container(
    settings: Optional[Any] = None,
    db: Optional[Any] = None,
) -> Container:
    """Build and wire application components in clean dependency order.

    Wiring sequence:
      settings -> db -> vector_strategy -> repository -> llm_provider ->
      extractor & chef -> ranker & recall -> lifecycle -> store -> orchestrator.

    Works fully offline when EMBEDDING_MODE=mock and LLM_PROVIDER=mock and a database
    handle is injected.
    """
    effective_settings = settings if settings is not None else config

    # 1. Database
    effective_db = db
    if effective_db is None:
        try:
            effective_db = config.get_database()
        except Exception as exc:
            logger.warning("Could not initialize default MongoDB database: %s", exc)
            effective_db = None

    # 2. Vector Strategy
    strategy_settings = None
    if isinstance(settings, dict):
        strategy_settings = settings
    elif settings is not None:
        strategy_settings = {
            "EMBEDDING_MODE": _get_setting(settings, "EMBEDDING_MODE", config.EMBEDDING_MODE),
            "EMBEDDING_MODEL": _get_setting(settings, "EMBEDDING_MODEL", config.EMBEDDING_MODEL),
            "EMBEDDING_DIMENSIONS": _get_setting(settings, "EMBEDDING_DIMENSIONS", config.EMBEDDING_DIMENSIONS),
            "VECTOR_INDEX_NAME": _get_setting(settings, "VECTOR_INDEX_NAME", config.VECTOR_INDEX_NAME),
            "VECTOR_TEXT_PATH": _get_setting(settings, "VECTOR_TEXT_PATH", config.VECTOR_TEXT_PATH),
            "VECTOR_NUM_CANDIDATES": _get_setting(settings, "VECTOR_NUM_CANDIDATES", config.VECTOR_NUM_CANDIDATES),
            "VOYAGE_API_KEY": _get_setting(settings, "VOYAGE_API_KEY", config.VOYAGE_API_KEY),
        }
    vector_strategy = get_vector_strategy(settings=strategy_settings)

    # 3. Repository
    repository = MemoryRepository(db=effective_db, strategy=vector_strategy)

    # 4. LLM Provider
    llm_provider = get_llm_provider(settings=effective_settings)

    # 5. Extractor and Chef
    extractor = MemoryExtractor(llm_provider=llm_provider)
    chef = Chef(llm_provider=llm_provider)

    # 6. Ranker & Recall (constructed before lifecycle to resolve circular dependency)
    ranker_fn = make_reranker(now_fn=utc_now)
    recall = MemoryRecall(
        repository=repository,
        rerank=ranker_fn,
        user_lookup=lambda uid: repository.get_user(uid),
    )

    # 7. Lifecycle (conditionally imported / wired if class exists)
    lifecycle = None
    try:
        from app.services import lifecycle as lifecycle_module
        if hasattr(lifecycle_module, "Lifecycle"):
            lifecycle = lifecycle_module.Lifecycle(
                repository=repository,
                recall=recall,
                now_fn=utc_now,
            )
    except Exception as exc:
        logger.debug("Lifecycle class could not be instantiated: %s", exc)

    # 8. Store (conditionally imported / wired if class exists)
    store = None
    try:
        from app.services import memory_store as store_module
        if hasattr(store_module, "MemoryStore"):
            store = store_module.MemoryStore(
                repository=repository,
                lifecycle=lifecycle,
                user_lookup=lambda uid: repository.get_user(uid),
                now_fn=utc_now,
            )
    except Exception as exc:
        logger.debug("MemoryStore class could not be instantiated: %s", exc)

    # 9. Orchestrator
    history_turns = int(_get_setting(effective_settings, "HISTORY_TURNS", 6))
    recall_limit = int(_get_setting(effective_settings, "RECALL_LIMIT", 5))
    max_message_chars = int(_get_setting(effective_settings, "MAX_MESSAGE_CHARS", 2000))

    orchestrator = ChatOrchestrator(
        extractor=extractor,
        store=store,
        recall=recall,
        ranker_fn=ranker_fn,
        chef=chef,
        repository=repository,
        now_fn=utc_now,
        history_turns=history_turns,
        recall_limit=recall_limit,
        max_message_chars=max_message_chars,
    )

    return Container(
        settings=effective_settings,
        db=effective_db,
        repository=repository,
        vector_strategy=vector_strategy,
        llm_provider=llm_provider,
        extractor=extractor,
        store=store,
        lifecycle=lifecycle,
        recall=recall,
        chef=chef,
        orchestrator=orchestrator,
    )


def health_check(container: Container) -> dict[str, Any]:
    """Inspect and report the operational status of core application subsystems."""
    db_reachable = False
    if container.db is not None:
        try:
            client = getattr(container.db, "client", None)
            if client is not None and hasattr(client, "admin"):
                client.admin.command("ping")
                db_reachable = True
            elif hasattr(container.db, "command"):
                container.db.command("ping")
                db_reachable = True
            else:
                db_reachable = True
        except Exception:
            db_reachable = False

    try:
        vector_status = container.repository.vector_index_status()
    except Exception:
        vector_status = "missing"

    mode_val = _get_setting(container.settings, "EMBEDDING_MODE", config.EMBEDDING_MODE)
    embedding_mode = str(mode_val).lower()

    provider_val = _get_setting(container.settings, "LLM_PROVIDER", config.LLM_PROVIDER)
    llm_provider_name = str(provider_val).lower()
    if type(container.llm_provider).__name__ == "MockLLMProvider":
        llm_provider_name = "mock"

    demo_mode = (embedding_mode == "mock" or llm_provider_name == "mock")

    return {
        "database_reachable": db_reachable,
        "vector_index_status": vector_status,
        "embedding_mode": embedding_mode,
        "llm_provider": llm_provider_name,
        "demo_mode": demo_mode,
    }
