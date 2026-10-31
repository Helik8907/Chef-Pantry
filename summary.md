# Project Summary: Chef

## 1. Project Overview
**Chef** is an AI-assisted culinary assistant built with Python, Streamlit, and MongoDB. The system features advanced episodic and semantic memory management to deliver tailored culinary interactions, recipes, and dietary planning.

Key architectural pillars:
- **UI Layer (`app/ui/`)**: Conversational Streamlit frontend featuring ChatGPT/Gemini-style chat interactions, session management, and dynamic memory retrieval visualization.
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
├── .devcontainer/
│   └── devcontainer.json
├── .env.example
├── .gitignore
├── .python-version
├── Agent.md
├── README.md
├── pyproject.toml
├── requirements.txt
├── summary.md
├── uv.lock
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   ├── main.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── chat.py
│   │       ├── demo.py
│   │       ├── memories.py
│   │       └── users.py
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
│   │   ├── db.py
│   │   ├── embedding_provider.py
│   │   ├── llm_client.py
│   │   ├── memory_repository.py
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── auto_embedding.py
│   │   │   ├── base.py
│   │   │   ├── claude_llm.py
│   │   │   ├── gemini_llm.py
│   │   │   ├── mock_embedding.py
│   │   │   ├── mock_llm.py
│   │   │   └── self_embedding.py
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── memory_repository.py
│   │       ├── message_repository.py
│   │       └── user_repository.py
│   ├── prompts/
│   │   ├── chef_answer.txt
│   │   ├── conflict_check.txt
│   │   ├── extraction.txt
│   │   └── safety_regenerate.txt
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth.py
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
│       └── components/
│           ├── __init__.py
│           ├── auth_view.py
│           ├── chat_panel.py
│           ├── memories_used_panel.py
│           ├── memory_management.py
│           └── sidebar.py
├── scripts/
│   ├── create_indexes.py
│   ├── reset_demo.py
│   └── seed_demo_data.py
├── tests/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── test_auth_routes.py
│   │   └── test_chat_routes.py
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
│       ├── test_auth.py
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
| `app/ui/` | Streamlit entrypoint (`main.py`) and modular components (`chat_panel`, `sidebar`, `auth_view`, `memory_management`) |
| `app/services/` | Business logic for chat orchestration, memory extraction, storage, recall, lifecycle, and conflict detection |
| `app/domain/` | Domain models, memory policies, ranking logic, and safety guardrails |
| `app/infra/` | MongoDB repository integration (`app/infra/repositories/`), database connector (`app/infra/db.py`), application config, LLM clients, and vector providers |
| `app/prompts/` | System text prompt templates for extraction, chef answering, conflict resolution, and safety verification |
| `app/api/` | FastAPI backend service with dependency injection and routes (`app/api/main.py`, `app/api/deps.py`, `app/api/routes/users.py`) |
| `.devcontainer/` | Dev Container configuration for local development tooling |
| `web/` | Placeholder for future static web frontend assets |
| `scripts/` | Database index creation, mock data seeding, and test state reset scripts |
| `uv.lock` | Resolved package versions used by Streamlit Cloud's `uv-sync` deployment |
| `tests/` | Unit tests for domain models/policies and service workflows |

---

## 3. Project Changelog & Recent Updates
- **2026-10-31 (Streamlit Cloud Runtime Dependencies)**:
  - Declared the app's production dependencies in `pyproject.toml` so Streamlit Cloud's selected `uv.lock` install includes Pydantic, MongoDB, Gemini, FastAPI, and Streamlit packages.
  - Regenerated `uv.lock` from the project dependency manifest.
  - Integrated the remote `.devcontainer/devcontainer.json` configuration while preserving the dependency fix.
- **2026-10-31 (Sidebar-Driven Memory Management Page Routing)**:
  - Added dedicated `🧠 Memory Management` button in [`app/ui/components/sidebar.py`](file:///e:/Project/Chef-Pantry/app/ui/components/sidebar.py) with active state highlighting.
  - Removed top-level tab navigation from [`app/ui/main.py`](file:///e:/Project/Chef-Pantry/app/ui/main.py) to keep the main view clean and distraction-free.
  - Implemented dynamic view routing: Clicking `🧠 Memory Management` in the sidebar renders the full Memory Management page on the main stage, while clicking `➕ New Chat` or any past conversation switches back to the Culinary Chat.
  - Added an in-page `← Back to Chat` header button in [`app/ui/components/memory_management.py`](file:///e:/Project/Chef-Pantry/app/ui/components/memory_management.py) for easy one-click return.
- **2026-10-31 (Dedicated Memory Management View & Sidebar Decluttering)**:
  - Removed the bulky sidebar memory manager (`🧠 Manage Memories`) from [`app/ui/components/sidebar.py`](file:///e:/Project/Chef-Pantry/app/ui/components/sidebar.py), restoring the ChatGPT/Claude layout.
  - Implemented dedicated **Memory Management** view component in [`app/ui/components/memory_management.py`](file:///e:/Project/Chef-Pantry/app/ui/components/memory_management.py).
  - Mounted dual-tab navigation in [`app/ui/main.py`](file:///e:/Project/Chef-Pantry/app/ui/main.py) (`💬 Culinary Chat` & `🧠 Memory Management`).
  - Added summary KPI cards (Active Memories, Protected Allergies, Taste Preferences, Pantry Items), real-time keyword search, type and status dropdown filters, formatted memory cards, and one-click `🗑️ Forget` soft deletion.
  - Ensured complete credential and technical ID sanitization across all memory view cards and tooltips.
- **2026-10-31 (Three Recipes and Persistent Preference Context)**:
  - Required exactly three concise recipe options in every food/cooking answer, including direct dish questions.
  - Made active dietary preferences always available to Chef alongside allergies, so each recipe is checked against saved diets and dislikes even when vector search would not rank those memories.
- **2026-10-31 (Memory Management UI and Pantry-Aware Recipe Suggestions)**:
  - Added a sidebar memory manager with manual memory creation, saved memory listing (including superseded memories), and confirmation-gated soft deletion through the lifecycle service.
  - Lowered pantry memory type priority and updated Chef's prompt to balance pantry ingredients with additional ingredients, including clear shopping notes.
- **2026-10-31 (Session ID & Technical Credentials Removal from UI)**:
  - Sanitized the sidebar interface in [`app/ui/components/sidebar.py`](file:///e:/Project/Chef-Pantry/app/ui/components/sidebar.py) to prevent technical identifiers and credentials from appearing anywhere in the user interface.
  - Removed hover tooltips displaying `Session ID: <sid>` on past conversation buttons.
  - Replaced button label fallbacks (`sid[:12]` and `Chat <sid[:8]>`) with clean conversational titles (`Conversation (<count>)` or `Conversation`).
  - Removed internal `User ID` display caption from the user profile dropdown, retaining only user-friendly name and email.
  - Removed internal database and vector index status diagnostic captions from user profile view.
- **2026-10-31 (Markdown Chat Answers with Plain Text Memory Embeddings)**:
  - Updated Chef and safety regeneration prompts to format chat answers as readable Markdown, including titled recipes, ingredient bullets, and numbered steps.
  - Added Markdown-to-plain-text normalization before memory persistence and query embedding; extraction and remembered-note prompts now request plain memory text.
- **2026-10-31 (Shorter Gemini Failure Wait)**:
  - Reduced the default Gemini request timeout from 60 seconds to 20 seconds.
  - Limited transient Gemini failures to two total attempts (one retry), so 504 errors surface to the chat sooner.
- **2026-10-31 (Unified Gemini Model Configuration)**:
  - Configured both extraction and Chef response generation to use the shared `MODEL` environment setting through `GEMINI_MODEL`.
  - Removed the separate `GEMINI_MODEL_EXTRACTION` and `GEMINI_MODEL_CHEF` settings from `.env`, `.env.development`, and `.env.example`.
- **2026-10-31 (Defensive Auth Error Handling for Atlas Connection / IP Firewall Errors)**:
  - Updated [`app/ui/components/auth_view.py`](file:///e:/Project/Chef-Pantry/app/ui/components/auth_view.py) with comprehensive try/except error boundaries intercepting `ServerSelectionTimeoutError` and `ConnectionFailure` during Sign In and Sign Up.
  - Formatted user-facing `st.error` messages instructing the user to check their MongoDB Atlas Network Access IP whitelist when SSL handshake or timeout failures occur.
  - Rebranded authentication headings to `"🍳 Chef"` and `"New to Chef?"`.
- **2026-10-31 (Gemini API Timeout Resiliency & AFC Warning Elimination)**:
  - Increased default LLM timeout from 30.0s to 60.0s in [`app/infra/config.py`](file:///e:/Project/Chef-Pantry/app/infra/config.py) and [`GeminiLLMProvider`](file:///e:/Project/Chef-Pantry/app/infra/providers/gemini_llm.py) to prevent premature read timeouts during complex structured generation.
  - Updated `_map_error` in [`GeminiLLMProvider`](file:///e:/Project/Chef-Pantry/app/infra/providers/gemini_llm.py) to classify socket read timeouts and timeout errors as retryable `_RetryableServerError`, allowing automatic exponential backoff retries.
  - Disabled automatic function calling via `types.AutomaticFunctionCallingConfig(disable=True)` across `structured_output` and `generate_text`, eliminating the warning log on standard generations.
- **2026-10-31 (Console Logging for Route & Page Visits)**:
  - Added HTTP middleware in [`app/api/main.py`](file:///e:/Project/Chef-Pantry/app/api/main.py) to log every incoming API request with method, path, response status, and execution duration in ms (`[ROUTE VISIT] GET /api/health -> 200 (1.2ms)`).
  - Added view/page access console logging in [`app/ui/main.py`](file:///e:/Project/Chef-Pantry/app/ui/main.py) for the Auth View (`[PAGE VISIT] 🔑 Auth View (Sign In / Register)`) and the Culinary Chat (`[PAGE VISIT] 💬 Culinary Chat | User: <user_id> | Session: <session_id>`).
  - Added session and authentication navigation logging in [`app/ui/components/sidebar.py`](file:///e:/Project/Chef-Pantry/app/ui/components/sidebar.py) and [`app/ui/components/auth_view.py`](file:///e:/Project/Chef-Pantry/app/ui/components/auth_view.py) for session switching, new chat creation, session deletion, login, and logout.
- **2026-10-31 (Gemini 3.8 Flash Upgrade & Developer API Schema Sanitization)**:
  - Upgraded default extraction and generation models from deprecated `gemini-2.5-flash` to **`gemini-3.8-flash`** across [`app/infra/config.py`](file:///e:/Project/Chef-Pantry/app/infra/config.py), [`app/infra/providers/gemini_llm.py`](file:///e:/Project/Chef-Pantry/app/infra/providers/gemini_llm.py), [`app/services/extraction.py`](file:///e:/Project/Chef-Pantry/app/services/extraction.py), [`app/services/chef.py`](file:///e:/Project/Chef-Pantry/app/services/chef.py), `.env`, `.env.development`, and `.env.example`, resolving the `404 NOT_FOUND` API error.
  - Implemented `_clean_schema_for_gemini` in [`app/infra/providers/gemini_llm.py`](file:///e:/Project/Chef-Pantry/app/infra/providers/gemini_llm.py) to recursively strip `additionalProperties` from Pydantic JSON schemas before passing to `GenerateContentConfig(response_schema=...)`, eliminating the Developer API mode schema rejection for models with dictionary fields (e.g. `CandidateMemory.structured`).
  - Verified 100% clean test execution across all 126 unit tests.
- **2026-10-31 (Updated Conversation Starter Prompts)**:
  - Updated new-chat starter prompts in [`app/ui/components/chat_panel.py`](file:///e:/Project/Chef-Pantry/app/ui/components/chat_panel.py) with customized suggestions:
    - 🍽️ "What should I cook for dinner tonight?"
    - 🥗 "Suggest a quick healthy lunch"
    - 🍳 "I have eggs, spinach and paneer. What can I make?"
    - 🥔 "Give me an easy snack idea"
- **2026-10-31 (MongoDB Unique Email Index & Duplicate Prevention)**:
  - Added unique sparse index on `users.email` (`self.db.users.create_index([("email", 1)], unique=True, sparse=True, background=True)`) in [`MemoryRepository.ensure_indexes`](file:///e:/Project/Chef-Pantry/app/infra/repositories/memory_repository.py#L246-L252) and provisioned it directly in MongoDB Atlas (`email_1`).
  - Updated [`UserRepository.upsert_user`](file:///e:/Project/Chef-Pantry/app/infra/repositories/user_repository.py#L45-L75) to intercept `pymongo.errors.DuplicateKeyError` and raise a clear `ValueError("An account with email '...' already exists.")`.
  - Updated [`app/api/routes/users.py`](file:///e:/Project/Chef-Pantry/app/api/routes/users.py) `POST /api/users` endpoint to validate email uniqueness and translate constraint errors into `409 Conflict` responses.
  - Verified duplicate email rejection against live MongoDB Atlas cluster and confirmed all 78 tests pass.
- **2026-10-31 (Rebranding to "Chef", Natural Conversational Flow & Response Embedding)**:
  - Rebranded the application from "Memory Chef" to **"Chef"** across the Streamlit UI ([`app/ui/main.py`](file:///e:/Project/Chef-Pantry/app/ui/main.py), [`app/ui/components/sidebar.py`](file:///e:/Project/Chef-Pantry/app/ui/components/sidebar.py), [`app/ui/components/chat_panel.py`](file:///e:/Project/Chef-Pantry/app/ui/components/chat_panel.py)), system prompt templates, and project documentation.
  - Refined the prompt instructions in [`app/prompts/chef_answer.txt`](file:///e:/Project/Chef-Pantry/app/prompts/chef_answer.txt) and attribution logic in [`app/services/chef.py`](file:///e:/Project/Chef-Pantry/app/services/chef.py) to provide a natural, conversational experience (like ChatGPT / Gemini).
  - Configured prompt and assistant attribution to naturally weave in `"I remembered that..."` (e.g. allergies, preferences, likes, pantry stock) whenever relevant memories are retrieved via vector search.
  - Extended [`ChefResponseSchema`](file:///e:/Project/Chef-Pantry/app/services/chef.py#L23-L33) and [`ChefResult`](file:///e:/Project/Chef-Pantry/app/services/chef.py#L34-L44) with `important_things_to_remember` to extract key culinary facts, recipes, and preferences from assistant responses.
  - Updated [`ChatOrchestrator`](file:///e:/Project/Chef-Pantry/app/services/chat_orchestrator.py) to embed and persist key facts from the assistant's response into MongoDB via [`MemoryStore`](file:///e:/Project/Chef-Pantry/app/services/memory_store.py) for future session recall.
- **2026-10-31 (Streamlined Conversational UI & Memory Inspector Removal)**:
  - Removed administrative `Memory Inspector` page (`app/ui/pages/memory_inspector.py`) and deleted `app/ui/pages/`.
  - Updated `app/ui/main.py` to remove tabbed navigation, rendering `render_chat_panel` directly as a full-width, clean conversational experience aligned with Gemini and ChatGPT.
  - Retained fully autonomous background memory extraction, conflict checking, TTL expiration, and cross-session memory recall within `ChatOrchestrator`, `MemoryStore`, and `MemoryRecall` without exposing raw internal database operations to end users.
  - Synchronized `README.md` and `summary.md` directory trees and architectural references.
- **2026-10-31 (Authentication Module, Routes & Account Management)**:
  - Extended domain `User` model in `app/domain/models.py` with `email`, `password_hash` (`Field(exclude=True)`), `updated_at`, and auth request/response schemas (`UserLoginRequest`, `UserRegisterRequest`, `TokenResponse`, `LogoutResponse`, `DeleteAccountResponse`).
  - Implemented core authentication services in `app/services/auth.py`:
    - `hash_password`: Salted PBKDF2-HMAC-SHA256 password hashing with 100,000 iterations.
    - `verify_password`: Constant-time comparison protecting against timing attacks.
    - `create_access_token` & `verify_access_token`: Cryptographically signed HMAC-SHA256 bearer session tokens.
    - `authenticate_user`: Credential verification by email and password.
    - `register_user`: Registration with email uniqueness check, handle sanitization/auto-generation, and password hashing.
    - `delete_user_account`: Permanent account deletion with cascade cleanup of memories and messages.
  - Updated `UserRepository` (`app/infra/repositories/user_repository.py`) and facade (`app/infra/memory_repository.py`) to query users by email and persist `password_hash`.
  - Added REST API authentication routes in `app/api/routes/auth.py` mounted at `/api/auth`:
    - `POST /api/auth/register` (register with email, password, display name)
    - `POST /api/auth/login` (authenticate with email and password, returning bearer token)
    - `POST /api/auth/logout` (session termination acknowledgement)
    - `GET /api/auth/me` (get profile for bearer token user)
    - `DELETE /api/auth/account` (delete authenticated user account with cascade)
  - Implemented Streamlit UI authentication flow:
    - Created `app/ui/components/auth_view.py` providing interactive Sign In and Sign Up tabs with masked password inputs and validation.
    - Updated `app/ui/main.py` with authentication gate: Unauthenticated visitors must sign in before accessing the Culinary Chat or Memory Inspector.
    - Updated `app/ui/components/sidebar.py` to display authenticated user email/handle, handle logout via session state reset, and provide an account deletion "Danger Zone" with confirmation.
  - Added comprehensive offline test coverage:
    - `tests/services/test_auth.py`: 9 unit tests verifying hashing, verification, token encoding, registration, email login, and deletion.
    - `tests/api/test_auth_routes.py`: 6 unit tests verifying `/register`, `/login`, `/logout`, `/me`, and `/account` route handlers.
- **2026-10-31 (User Document Deserialization Fix in Sidebar)**:
  - Updated `app/ui/components/sidebar.py` to defensively deserialize the MongoDB `dict` returned by `UserRepository.get_user` into a Pydantic `User` model (`User.model_validate(raw_user)`).
  - Resolved `AttributeError: 'dict' object has no attribute 'display_name'`.
  - Removed obsolete `auto_supersede_confirmed` field from `UserSettings` reconstruction.
- **2026-10-31 (Modern Chatbot UI Layout Restructuring)**:
  - Restructured `app/ui/components/sidebar.py` to match ChatGPT/Claude layouts:
    - Prominent `➕ New Chat` primary action button at the top.
    - Chronological, clickable past conversation list with active session highlighting and inline `🗑️` deletion buttons.
    - User profile footer with handle display, expandable memory and unit preferences, database status indicator, and `🚪 Log Out` button.
  - Updated `app/ui/components/chat_panel.py`:
    - Clean default "New Chat" screen featuring a welcoming hero banner and 4 quick-prompt suggestion cards (vegetarian dinner, allergy declaration, pantry cook, and feedback reporting).
    - Automatic history loading when selecting previous sessions from the sidebar.
    - Compact, non-intrusive `🧠 Memories Recalled` collapsible expanders directly beneath assistant replies displaying recalled dietary/taste memories and reasoning.
  - Updated `app/ui/main.py`:
    - Dedicated authentication screen (`render_login_view`) for user handle input upon logout.
    - Full-width modern chat experience with clean tab navigation to Memory Inspector.
- **2026-10-31 (Streamlit sys.path Root Resolution Fix)**:
  - Added project root resolution (`sys.path.insert(0, str(ROOT_DIR))`) to `app/ui/main.py` and `app/ui/pages/memory_inspector.py`.
  - Resolves `ModuleNotFoundError: No module named 'app'` when running `streamlit run app/ui/main.py` directly from any working directory.
- **2026-10-31 (Streamlit Frontend Implementation & Dependency Setup)**:
  - Added `streamlit>=1.30.0` to `requirements.txt` and installed `streamlit 1.66.1` into the project virtual environment.
  - Implemented the modular Streamlit frontend:
    - `app/ui/main.py`: Main application controller with `@st.cache_resource` container initialization, dual-tab layout (Culinary Chat & Memory Inspector), and responsive split view.
    - `app/ui/components/sidebar.py`: User profile selection/creation (`demo_user` default), unit preferences (`metric`/`imperial`), memory retrieval toggle, chat session manager (`➕ New Chat Session`, session history picker), and live database/vector status diagnostics.
    - `app/ui/components/chat_panel.py`: Multi-turn chat message rendering, `st.chat_input`, `orchestrator.handle_message` execution, and interactive approval/rejection widgets for `pending_confirmations`.
    - `app/ui/components/memories_used_panel.py`: Real-time memory attribution panel with allergen guardrail alerts, score breakdowns (`similarity`, `recency_boost`, `rating_boost`, `type_priority_boost`, `usage_bonus`), memory store event counters, and latency trace details.
    - `app/ui/pages/memory_inspector.py`: Memory auditing and inspection page with metric cards, text keyword filtering, type and status dropdown filters, TTL expiration dates, and one-click soft-delete (`forget`) capability.
  - Verified 100% clean imports across all UI modules and full passing status across all 111 unit tests.
- **2026-10-31 (MongoDB Timezone Awareness & Dual Identifier Resolution)**:
  - Configured `MongoClient(..., tz_aware=True)` in `app/infra/db.py` to ensure PyMongo decodes MongoDB BSON dates into timezone-aware UTC datetimes.
  - Implemented `ensure_utc_datetimes` utility in `app/infra/repositories/base.py` to defensively ensure timezone awareness across all repository queries.
  - Updated `app/infra/repositories/user_repository.py`:
    - `get_user`: Supports querying by either custom user handle (`user_id`) or MongoDB document `_id` (string or BSON `ObjectId`), resolving `404` errors when clients pass either identifier.
    - Attached UTC timezone info to naive datetimes, resolving `500 Internal Server Error` (`ValidationError` on `created_at`).
    - `delete_user`: Enhanced identifier lookup to match and delete by either `user_id` or `_id` before executing cascade deletions.
  - Updated `app/infra/repositories/memory_repository.py` and `app/infra/repositories/message_repository.py` with `ensure_utc_datetimes` to protect all returned documents.
- **2026-10-31 (Modular Infrastructure Repositories & Database Connector)**:
  - Extracted MongoDB database client connection and ping diagnostics from `app/infra/config.py` into a dedicated `app/infra/db.py` module (`get_mongo_client`, `get_database`, `close_mongo_client`, `ping_database`).
  - Modularized repository layers into dedicated files under `app/infra/repositories/`:
    - `app/infra/repositories/base.py`: Custom exceptions (`VectorIndexNotReadyError`, `RateLimitError`), retry inspector (`is_rate_limit_error`), and vector search aggregation pipeline builder (`build_vector_search_pipeline`).
    - `app/infra/repositories/user_repository.py`: Dedicated `UserRepository` handling user retrieval (`get_user`), upsert (`upsert_user`), and cascade deletion (`delete_user`).
    - `app/infra/repositories/message_repository.py`: Dedicated `MessageRepository` handling chat turn storage (`insert_message`), history retrieval (`list_messages`), and session summaries (`list_sessions`).
    - `app/infra/repositories/memory_repository.py`: Dedicated `MemoryRepository` handling vector index creation, search, memory CRUD, and lifecycle status transitions.
    - `app/infra/repositories/__init__.py`: Clean package exports for specialized repositories and exceptions.
  - Refactored `app/infra/memory_repository.py` into a lightweight composite facade delegating to the specialized repositories to ensure 100% backward compatibility across all services and tests.
  - Updated `app/api/deps.py` and `app/api/routes/users.py` to use `UserRepository` directly via dependency injection.
- **2026-10-31 (Pydantic Model Assignment Recursion Fix)**:
  - Updated `app/domain/models.py` inside `apply_lifecycle_and_allergy_rules` to use `object.__setattr__` for setting `protected` and `expires_at` on allergy memories, resolving a `RecursionError` during assignment validation.
  - Verified 100% test pass rate across the full test suite (105 of 105 tests passing).
- **2026-10-31 (User Management API Routes & Cascade Deletion)**:
  - Added `delete_user(user_id: str, cascade: bool = True) -> bool` to `app/infra/memory_repository.py` with support for cascade deletion of all user memories and messages.
  - Implemented FastAPI dependency management in `app/api/deps.py` (`get_container`, `set_container`, `get_repository`).
  - Implemented user REST API endpoints in `app/api/routes/users.py`:
    - `POST /api/users` (Add user with unique `user_id` validation and 409 Conflict handling).
    - `GET /api/users/{user_id}` (Retrieve user record with 404 Not Found handling).
    - `DELETE /api/users/{user_id}` (Delete user with optional `cascade=true` query param, 404 handling).
  - Configured FastAPI application in `app/api/main.py` with CORS middleware, lifespan initialization, and `/api/health` check.
  - Added `fastapi>=0.110.0` and `uvicorn>=0.28.0` to `requirements.txt`.
- **2026-10-31 (Index Provisioning Collection Creation & Dev Env Priority)**:
  - Updated `app/infra/memory_repository.py` to ensure target collections (`memories`, `users`, `messages`) exist before calling `create_search_index`, preventing `NamespaceNotFound` errors on fresh databases.
  - Updated `app/infra/config.py` to prioritize `.env.development` / `.env.devlopment` before `.env` with `override=True`.
  - Synchronized `.env` with `.env.development`.
- **2026-10-31 (Database Collection Schemas Documentation)**:
  - Documented full database schemas in `README.md` under `## 🗄️ Database Collection Schemas`:
    - `memories`: Comprehensive schema breakdown, structured payloads per memory type (`allergy`, `preference`, `meal_outcome`, `pantry_item`, `temporary_context`), and vector/TTL/compound index specifications.
    - `messages`: Conversational schema with memory citation attribution (`memories_used`), turns, and session compound index.
    - `users`: User profile, measurement unit settings, memory toggle, and unique index definitions.
- **2026-10-31 (MongoDB Password URL-Encoding Safeguard)**:
  - Updated `app/infra/config.py` to automatically URL-encode `MONGO_PASSWORD` using `urllib.parse.quote_plus` when replacing the `<db_password>` placeholder in `RAW_MONGO_URI`, preventing URI parsing breakages when passwords include special characters.
- **2026-10-31 (Environment Loading & Config Resilience)**:
  - Updated `app/infra/config.py` to search for development environment files (`.env.development`, `.env.devlopment`) before falling back to `.env.example`.
  - Created `.env` from `.env.devlopment` to ensure MongoDB credentials and connection URIs load reliably across CLI and test runners.
- **2026-10-31 (Index Provisioning Script Path Resolution)**:
  - Added project root path insertion to `sys.path` in `scripts/create_indexes.py` using `pathlib.Path` to support direct script execution (`python scripts/create_indexes.py`) without requiring explicit `PYTHONPATH` or `python -m` invocation.
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
  - Updated `app/infra/config.py` with LLM generation configurations (`LLM_PROVIDER`, shared `MODEL`/`GEMINI_MODEL`, `LLM_TEMPERATURE_EXTRACTION`, `LLM_TEMPERATURE_CHEF`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_TIMEOUT_SECONDS`).
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
