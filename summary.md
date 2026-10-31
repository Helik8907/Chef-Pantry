# Project Summary: Memory Chef

## 1. Project Overview
**Memory Chef** is an AI-assisted culinary assistant built with Python, Streamlit, and MongoDB. The system features advanced episodic and semantic memory management to deliver tailored culinary interactions, recipes, and dietary planning.

Key architectural pillars:
- **UI Layer (`app/ui/`)**: Interactive Streamlit frontend featuring chat interactions, memory inspection, and dynamic memory retrieval visualization.
- **Service Layer (`app/services/`)**: Orchestration of conversation flows, culinary prompt synthesis, memory extraction, memory storage, lifecycle management, conflict detection, and memory recall.
- **Domain Layer (`app/domain/`)**: Core entities, memory scoring/ranking algorithms, safety filters, and operational policies.
- **Infrastructure Layer (`app/infra/`)**: MongoDB memory repository, LLM clients (Anthropic Claude / mock fallbacks), and vector embedding providers.
- **Prompt Engineering (`app/prompts/`)**: Modular system prompts for extraction, answer generation, conflict resolution, and safety moderation.
- **API & Web (`app/api/`, `web/`)**: Placeholder endpoints and assets for future FastAPI backend service and custom HTML/JS frontend.
- **Operations & Verification (`scripts/`, `tests/`)**: Index setup, mock seeding, and test fixtures for domain and service layers.

---

## 2. Directory Tree & File Map

```
.
├── .env.example
├── .gitignore
├── .python-version
├── Agent.md
├── README.md
├── pyproject.toml
├── requirements.txt
├── summary.md
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── chat.py
│   │       ├── demo.py
│   │       └── memories.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── policies.py
│   │   ├── privacy.py
│   │   ├── ranker.py
│   │   └── safety.py
│   ├── infra/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── embedding_provider.py
│   │   ├── llm_client.py
│   │   ├── memory_repository.py
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── auto_embedding.py
│   │       ├── base.py
│   │       ├── claude_llm.py
│   │       ├── gemini_llm.py
│   │       ├── mock_embedding.py
│   │       ├── mock_llm.py
│   │       └── self_embedding.py
│   ├── prompts/
│   │   ├── chef_answer.txt
│   │   ├── conflict_check.txt
│   │   ├── extraction.txt
│   │   └── safety_regenerate.txt
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chef.py
│   │   ├── chat_orchestrator.py
│   │   ├── conflict.py
│   │   ├── container.py
│   │   ├── extraction.py
│   │   ├── lifecycle.py
│   │   ├── memory_recall.py
│   │   └── memory_store.py
│   └── ui/
│       ├── __init__.py
│       ├── main.py
│       ├── components/
│       │   ├── __init__.py
│       │   ├── chat_panel.py
│       │   ├── memories_used_panel.py
│       │   └── sidebar.py
│       └── pages/
│           ├── __init__.py
│           └── memory_inspector.py
├── scripts/
│   ├── create_indexes.py
│   ├── reset_demo.py
│   └── seed_demo_data.py
├── tests/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── test_policies.py
│   │   ├── test_privacy.py
│   │   ├── test_ranker.py
│   │   └── test_safety.py
│   ├── infra/
│   │   ├── __init__.py
│   │   └── test_embedding_strategies.py
│   └── services/
│       ├── __init__.py
│       ├── test_generation.py
│       ├── test_lifecycle.py
│       ├── test_memory_recall.py
│       ├── test_memory_store.py
│       └── test_orchestrator.py
└── web/
    ├── index.html
    ├── css/
    │   └── styles.css
    └── js/
        ├── api.js
        ├── chat.js
        └── inspector.js
```

### Component Details
| Directory / File | Description |
|---|---|
| `app/ui/` | Streamlit entrypoint (`main.py`), reusable chat/memory UI panels, and memory inspector page |
| `app/services/` | Business logic for chat orchestration, memory extraction, storage, recall, lifecycle, and conflict detection |
| `app/domain/` | Domain models, memory policies, ranking logic, and safety guardrails |
| `app/infra/` | MongoDB repository integration, application configuration, LLM clients, and vector embedding providers |
| `app/prompts/` | System text prompt templates for extraction, chef answering, conflict resolution, and safety verification |
| `app/api/` | Placeholder for future FastAPI endpoints |
| `web/` | Placeholder for future static web frontend assets |
| `scripts/` | Database index creation, mock data seeding, and test state reset scripts |
| `tests/` | Unit tests for domain models/policies and service workflows |

---

## 3. Project Changelog & Recent Updates
- **2026-10-31 (Project Documentation & README Initialization)**:
  - Created comprehensive project documentation in `README.md`:
    - Overview of Memory Chef problem statement and architecture.
    - Deep dive into multi-type structured memories, ranking formula, and allergen safety guardrails.
    - Architectural layout and directory map.
    - Step-by-step setup, configuration reference, index provisioning, and test execution instructions.
    - Cross-references to `summary.md` and `agent.md`.
- **2026-10-31 (Memory Store & Lifecycle Implementation)**:
  - Implemented pure Python domain privacy and secret redaction in `app/domain/privacy.py`:
    - `RedactionResult` model and `redact_sensitive` function.
    - Heuristic masking for API keys (`[REDACTED_API_KEY]`), credit card numbers (`[REDACTED_CARD]`), emails (`[REDACTED_EMAIL]`), phone numbers (`[REDACTED_PHONE]`), passwords (`[REDACTED_PASSWORD]`), and government IDs (`[REDACTED_GOV_ID]`).
    - Explicit preservation of culinary allergens (peanuts, shellfish, gluten, dairy, etc.).
    - `blocked=True` indicator when secret tokens dominate the input.
  - Appended repository persistence and scoping methods in `app/infra/memory_repository.py`:
    - `update_fields`: user-scoped updates updating `updated_at`.
    - `link_supersede`: links old superseded document to new document with transaction fallback to safe ordering.
    - `soft_delete`: sets `status="deleted"`, records `deleted_at`, and unsets `embedding`.
    - `hard_delete`: removes memory document scoped by `user_id`.
    - `find_duplicate_candidates`: retrieves active, non-expired memories matching normalized dedupe keys.
    - `find_expired`: retrieves active memories with `expires_at <= now`.
    - `get_memory_by_id_scoped`: guarantees zero cross-user access.
  - Implemented `app/services/lifecycle.py`:
    - `Lifecycle` service coordinating `find_correction_target`, `supersede`, `forget`, `revise`, `expire_now`, `purge_expired`, and `list_expiring`.
    - Threshold gating (`CORRECTION_SIMILARITY_THRESHOLD`, `CORRECTION_MARGIN`) for single vs ambiguous vs none target categorization.
    - Protected allergy confirmation enforcement on automated supersede and revisions.
    - Dangling reference elimination during memory deletion.
  - Implemented `app/services/memory_store.py`:
    - `MemoryStore` service implementing candidate ingestion pipeline: memory-enabled check, redaction, confidence gating (`MIN_STORE_CONFIDENCE`), structured deduplication with timestamp refreshing, correction resolution routing, and policy-driven memory construction (`compute_expires_at`, `is_protected`).
    - Exposed `confirm_pending` for user-approved changes.
    - Suppressed sensitive and allergy text logging at info level.
  - Implemented comprehensive unit tests:
    - `tests/domain/test_privacy.py`: 7 tests covering all redaction patterns, allergen preservation, and secret blocking.
    - `tests/services/test_lifecycle.py`: 9 tests covering soft/hard delete, allergy forget, supersede links, allergy confirmation, dangling reference cleanup, revise, expiry, and user scoping.
    - `tests/services/test_memory_store.py`: 6 tests covering memory-disabled bypass, deduplication refresh, TTL/protection policies, confidence filtering, error isolation, and correction/allergy flows.
- **2026-10-31 (Chat Orchestrator & Container Composition Root Implementation)**:
  - Extended domain models in `app/domain/models.py`:
    - Added `StepTiming` (`step`, `ms`) and `TraceInfo` (`extracted`, `stored_ids`, `superseded`, `duplicates_refreshed`, `skipped`, `recalled_count`, `always_applied_ids`, `timings`, `degraded_steps`).
    - Extended `ChatResponse` with optional fields: `pending_confirmations`, `ambiguous_corrections`, `warnings`, `trace`, and `message_id`.
  - Appended repository persistence methods in `app/infra/memory_repository.py`:
    - `insert_message`: persists user and assistant chat messages into `messages` collection.
    - `list_messages`: queries session chat history ordered oldest to newest.
    - `list_sessions`: aggregates user sessions with first/last message timestamps and message counts.
    - `get_user`: retrieves user document by `user_id`.
    - `upsert_user`: creates or updates user profile and settings.
  - Implemented `app/services/chat_orchestrator.py`:
    - `ChatOrchestrator` coordinating input validation, session history loading, user persistence, extraction, pre-recall candidate storage, recall with ranking, chef answer synthesis, memory usage tracking, assistant persistence, and failure isolation across all steps.
    - Exposes `handle_message`, `confirm_change`, `get_history`, and `list_sessions`.
  - Implemented `app/services/container.py`:
    - `Container` dataclass and `build_container` composition root resolving circular dependencies between lifecycle and recall cleanly.
    - Supports fully offline mock mode (`EMBEDDING_MODE=mock`, `LLM_PROVIDER=mock`, injected test db).
    - `health_check` inspecting database reachability, vector index status, embedding mode, LLM provider, and demo mode.
  - Implemented unit tests in `tests/services/test_orchestrator.py`:
    - 11 comprehensive offline unit tests verifying happy path, store-before-recall ordering, memory-disabled bypass, failure isolation, empty/long inputs, pending/ambiguous change propagation, safety warning handling, and container composition.
- **2026-10-31 (Gemini Generation Pipeline & Safety Guardrails Implementation)**:
  - Added `google-genai` to `requirements.txt`.
  - Updated `app/infra/config.py` with LLM generation configurations (`LLM_PROVIDER`, `GEMINI_MODEL_EXTRACTION`, `GEMINI_MODEL_CHEF`, `LLM_TEMPERATURE_EXTRACTION`, `LLM_TEMPERATURE_CHEF`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_TIMEOUT_SECONDS`).
  - Implemented `app/infra/llm_client.py`: abstract `LLMProvider` interface (`structured_output`, `generate_text`), custom exceptions (`LLMError`, `LLMOutputError`, `LLMRateLimitError`), singleton factory `get_llm_provider`, and `reset_llm_provider`.
  - Implemented `app/infra/providers/gemini_llm.py`: `GeminiLLMProvider` leveraging official `google-genai` SDK, structured output parsing with `parsed` and JSON fallback, token limit truncation retry handling, and backoff retries for rate limits and 5xx errors.
  - Implemented `app/infra/providers/mock_llm.py`: deterministic, offline `MockLLMProvider` parsing regex patterns for allergies, preferences, pantry, outcomes, and citations for `ExtractionResult` and `ChefResponseSchema`.
  - Implemented `app/domain/safety.py`: heuristic allergen detection (`check_allergen_conflicts`), `ALLERGEN_SYNONYMS` map, boundary regex matching, and prefix/suffix negation handling (`-free`, `without`).
  - Implemented system prompt files: `app/prompts/extraction.txt`, `app/prompts/chef_answer.txt`, and `app/prompts/safety_regenerate.txt`.
  - Implemented `app/services/extraction.py`: `MemoryExtractor` with retry-on-output-error, non-crashing guarantee, and post-processing (clamping, tag normalization, TTL defaults).
  - Implemented `app/services/chef.py`: `Chef` service, structured output schemas (`ChefResponseSchema`, `ChefResult`), memory citation validation, "Because I remembered" inclusion, and two-step safety regeneration loop with safe fallback.
  - Implemented `tests/domain/test_safety.py` and `tests/services/test_generation.py` with 16 comprehensive unit tests passing cleanly.
- **2026-10-31 (Policies & Ranker Domain Module Implementation)**:
  - Implemented policies, ranking rules, multi-factor scoring, explanations, and reranker factory touching strictly domain and test files:
    - `app/domain/policies.py`:
      - `TypePolicy` frozen dataclass defining `ttl`, `protected`, `auto_supersede_allowed`, `requires_confirmation_to_change`, `type_priority`, `recency_half_life_days`, and `always_apply`.
      - `RankingWeights` frozen dataclass validating sum to 1.0.
      - `DEFAULT_WEIGHTS` configuration (0.55 similarity, 0.15 recency, 0.15 rating_signal, 0.10 type_priority, 0.05 usage).
      - `POLICIES` dictionary keyed by `MemoryType` as the single source of truth for all per-type rules.
      - Functions: `get_policy`, `compute_expires_at`, `is_protected`, `can_auto_supersede`, and `requires_confirmation`.
    - `app/domain/ranker.py`:
      - `Candidate` frozen dataclass pairing `Memory` with raw similarity.
      - `score_memory` pure function computing clamped similarity, exponential half-life recency decay, bidirectional rating salience boost (`abs(rating - 3) / 2`) with structured feedback bump, type priority, log-scaled usage bonus, and non-cooking pantry dampening ($0.6\times$).
      - `explain` producing prioritized human-readable reasons (capped at 4).
      - `rank` handling lifecycle filtering (`Memory.is_active(now)`), deterministic tie-breaking (final score $\to$ similarity $\to$ created_at $\to$ id), `max_per_type` diversity limits, `min_score` cutoff, and `top_k` limiting.
      - `make_reranker` factory creating a callable compatible with `MemoryRecall.rerank`.
    - `tests/domain/test_policies.py`:
      - Appended 8 unit tests covering weight validation, policy invariants, demo TTL overrides, expiration capping, and helper methods.
    - `tests/domain/test_ranker.py`:
      - 10 offline unit tests covering recency decay, meal outcome rating boosts, feedback text bumps, lifecycle exclusion, deterministic tie-breaking, max per type and min score filtering, cooking intent dampening, explanation reasons, weight customization, and reranker callable compatibility.
- **2026-10-31 (Vector Search & Memory Recall Module Implementation)**:
  - Implemented the vector search and memory recall module touching only the requested infrastructure, script, service, and test files:
    - `app/infra/memory_repository.py`:
      - `MemoryRepository` class with constructor-injected `Database` and `VectorStrategy`.
      - Connection, indexing, and CRUD methods: `insert_memory`, `get_memory`, `list_memories`, `update_status`, `mark_used`, `delete_memory`, `get_active_by_type`, `ensure_indexes`, `vector_index_status`, and `vector_search`.
      - Pure function `build_vector_search_pipeline` supporting pre-filters (`user_id`, `status`, `type`), over-fetch capping, expiration `$match`, projection excluding `embedding` with `{"$meta": "vectorSearchScore"}` as `_score`, and trimming `$limit`.
      - Error handling: Defined `VectorIndexNotReadyError`, retry backoff for rate-limit errors via `run_with_backoff`, and suppressed sensitive text logging at info level.
      - Enforced PyMongo >= 4.7 requirement check during index initialization.
    - `scripts/create_indexes.py`:
      - Executable script verifying PyMongo >= 4.7, provisioning vector search and operational indexes, and polling index readiness with timeouts and clear Atlas M10+ automated embedding notices.
    - `app/services/memory_recall.py`:
      - `MemoryRecall` service with constructor injection of `repository`, optional pluggable `rerank` callable (defaulting to descending similarity sort), and user lookup.
      - `recall` method: Enforces `user.settings.memory_enabled` check, fetches always-applied active allergies via `get_active_by_type`, executes vector search, excludes deleted/superseded/expired memories, de-duplicates always-applied from recalled, builds `RecalledMemory` models, and handles `VectorIndexNotReadyError` gracefully with warnings.
      - `mark_recalled` helper to record usage timestamps and increments for orchestrator post-generation.
    - `tests/services/test_memory_recall.py`:
      - 8 comprehensive offline unit tests covering pipeline construction, over-fetch limits, allergy inclusion and de-duplication, lifecycle exclusions, memory disable short-circuiting, custom reranker callables, `VectorIndexNotReadyError` warning handling, and `mark_recalled` tracking.
- **2026-10-31 (Embedding & Vector Strategy Module Implementation)**:
  - Implemented the embedding and vector strategy module supporting three distinct modes (`mock`, `auto`, and `self`):
    - `app/infra/providers/base.py`: Abstract `VectorStrategy` class, `EmbeddingError` exception, and `run_with_backoff` exponential retry utility.
    - `app/infra/providers/auto_embedding.py`: `AutoEmbeddingStrategy` for MongoDB Atlas Automated Embedding (validates Voyage models: `voyage-3-large`, `voyage-3.5`, `voyage-3.5-lite`, text path `text`, leaves documents unchanged without embedding field).
    - `app/infra/providers/self_embedding.py`: `SelfEmbeddingStrategy` with lazy `voyageai` client import, input type discrimination (`query` vs `document`), batching, retry with backoff, dimension validation, and secure key handling.
    - `app/infra/providers/mock_embedding.py`: `MockEmbeddingStrategy` with deterministic MD5 token-hash bag-of-words accumulation, L2-normalization, zero network calls, and `cosine_similarity` test helper.
    - `app/infra/embedding_provider.py`: Factory `get_vector_strategy` with mode dispatch, parameter validation, singleton caching, clear Atlas M10+ cluster advisory, and `reset_vector_strategy` utility.
    - `app/infra/config.py`: Added embedding settings (`EMBEDDING_MODE`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `VECTOR_INDEX_NAME`, `VECTOR_TEXT_PATH`, `VECTOR_NUM_CANDIDATES`, `VOYAGE_API_KEY`) and mirrored them in `.env.example`.
    - `tests/infra/test_embedding_strategies.py`: 25 comprehensive offline unit tests covering determinism, cosine similarity, index definition schemas, search stage generation, list `$in` filter translation, factory behavior, and backoff retries.
- **2026-10-31 (MongoDB Infrastructure & Config Connector)**:
  - Installed `pymongo`, `dnspython`, and `python-dotenv` into the project virtual environment.
  - Implemented application environment loading and MongoDB connector in `app/infra/config.py`:
    - Reads `MONGO_URI`, `MONGO_PASSWORD`, `MONGO_DB_NAME`, `GEMINI_API_KEY`, and `MODEL` from `.env` / `.env.example`.
    - Handles `<db_password>` substitution in the connection URI automatically.
    - Provides singleton client getter (`get_mongo_client`), database getter (`get_database`), and console ping test (`test_mongo_connection`).
  - Verified connection to MongoDB Atlas (`travelandtourisum.dmr7st3.mongodb.net`, database: `chef_pantry`) with console status notification (`[SUCCESS] Connected to MongoDB server successfully!`).
- **2026-10-31 (Domain Models & Model Validation Tests)**:
  - Implemented pure-Python domain data models in `app/domain/models.py` using Pydantic v2:
    - Enums: `MemoryType`, `MemoryStatus`, `MemorySource`, `Visibility`, `MessageRole`.
    - User models: `User`, `UserSettings`.
    - Core memory models & helpers: `Memory`, `CandidateMemory`, `ExtractionResult`, `MemoryUsed`, `ScoreBreakdown`, `RecalledMemory`, `MemoryUpdateRequest`.
    - Chat models: `Message`, `ChatRequest`, `ChatResponse`.
    - Structured helpers: `AllergyData`, `PreferenceData`, `MealOutcomeData`, `PantryData`, `TemporaryContextData`.
    - Zero I/O and pure Python, with 24-character hexadecimal ObjectId compatibility, UTC timezone enforcement, tag normalization, and allergy auto-protection.
  - Implemented unit tests in `tests/domain/test_policies.py` verifying model validation rules (allergy protection & expiry nullification, tag cleaning, empty text rejection, `is_expired`/`is_active` logic, and naive datetime rejection).
- **2026-10-31 (Commit `6171e67`)**:
  - Updated `.gitignore` with comprehensive ignore rules for Node.js, Next.js, Yarn, build/coverage artifacts, environment files, and Python environments.
  - Removed `docs/` directory (`docs/architecture.md` and `docs/demo_script.md`).
  - Synchronized `summary.md` to reflect the updated directory structure.
- **2026-10-31 (Initial Scaffold)**:
  - Initialized "Memory Chef" project structure with root set to current working directory (`Chef-Pantry`).
  - Created 20 directories and 66 completely empty (0-byte) files adhering strictly to the required layout.
  - Reset `.gitignore` and `README.md` to empty state as instructed.
  - Initialized `summary.md` with full architecture, file map, and changelog per `Agent.md` operational guidelines.
