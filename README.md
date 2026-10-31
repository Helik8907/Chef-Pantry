# Memory Chef 🍳🧠

> An intelligent, context-aware culinary assistant powered by episodic and semantic memory management, MongoDB Atlas Vector Search, and Google Gemini.

---

## 📖 Overview

Standard conversational AI assistants suffer from context amnesia between sessions—they forget dietary constraints, repetitive preferences, spice tolerances, available pantry stock, and past cooking outcomes.

**Memory Chef** solves this by treating culinary knowledge and user context as a living, structured memory graph. It automatically extracts, categorizes, deduplicates, and ranks user memories to personalize recipes, recommend meal plans, and enforce critical dietary and allergen safety boundaries.

---

## ✨ Key Features

- **Multi-Type Structured Memory System**:
  - 🚫 **Allergies**: Strictly protected, persistent, and automatically injected into all culinary reasoning steps.
  - 🥗 **Preferences**: Cuisines, spice levels, dietary philosophies, and kitchen habits.
  - 🍲 **Meal Outcomes**: Historical feedback, 1–5 star ratings, and recipe adjustment learnings.
  - 🥫 **Pantry Items**: Real-time tracking of ingredients on hand with expiration timestamps.
  - ⏱️ **Temporary Context**: Short-term goals and event-driven notes with automatic TTL expiration.

- **Multi-Factor Memory Ranking & Recall**:
  - Memory candidates are retrieved using vector similarity and rescored using a 5-factor formula:
    - **Vector Similarity (55%)**: Clamped semantic relevance.
    - **Recency Decay (15%)**: Half-life decay based on memory age.
    - **Rating Salience (15%)**: Bidirectional boost for high-impact recipes ($\le 2$ or $\ge 4$ stars).
    - **Type Priority (10%)**: Tiered baseline priority across memory types.
    - **Usage Frequency (5%)**: Log-scaled utility bonus for frequently referenced memories.
  - Contextual pantry dampening ($0.6\times$) applied when queries do not exhibit cooking intent.

- **Dietary & Allergen Safety Guardrails**:
  - Deterministic allergen detection with boundary matching and negative phrasing handling (`-free`, `without`).
  - Two-step safety regeneration loop to re-synthesize or redact unsafe recipe suggestions.

- **Flexible Embedding & Vector Search**:
  - **Atlas Automated Embedding (`auto`)**: Native MongoDB Atlas Voyage AI vector management.
  - **Client-Side Embedding (`self`)**: Direct integration with Voyage AI embeddings (`voyage-3.5-lite`).
  - **Offline Deterministic Mock (`mock`)**: Zero-network hash bag-of-words embedding for testing and offline development.

- **Clean Dependency Injection & Container Root**:
  - Centralized composition root (`app/services/container.py`) providing fully testable and isolated orchestration.

---

## 🏗️ Project Architecture

```
.
├── app/
│   ├── api/                   # REST API routes and endpoints (FastAPI)
│   ├── domain/                # Core domain models, policies, ranking, and safety logic
│   │   ├── models.py          # Pydantic v2 schemas for memories, users, and chat
│   │   ├── policies.py        # Per-type lifecycle, TTL, and protection policies
│   │   ├── ranker.py          # Multi-factor scoring, explanations, and reranking
│   │   └── safety.py          # Allergen heuristics and safety validation
│   ├── infra/                 # Database, configuration, and external providers
│   │   ├── config.py          # Environment configuration and MongoDB connection
│   │   ├── embedding_provider.py # Vector strategy factory
│   │   ├── llm_client.py      # LLM provider interface and factory
│   │   ├── memory_repository.py # MongoDB CRUD and vector search aggregation
│   │   └── providers/         # Concrete LLM and embedding providers
│   ├── prompts/               # System prompt templates
│   ├── services/              # Business logic and application workflows
│   │   ├── chat_orchestrator.py # Conversation workflow coordinator
│   │   ├── chef.py            # Recipe synthesis and safety regeneration
│   │   ├── container.py       # Composition root and service wiring
│   │   ├── extraction.py      # Structured memory extraction
│   │   └── memory_recall.py   # Vector search and candidate reranking
│   └── ui/                    # Streamlit frontend application
│       ├── components/        # Chat, sidebar, auth, and memory management components
│       └── main.py            # Streamlit application entrypoint
├── scripts/
│   ├── create_indexes.py      # MongoDB Atlas index provisioning script
│   ├── reset_demo.py          # Database state reset utility
│   └── seed_demo_data.py      # Demo fixture and memory seeder
├── tests/                     # Unit and integration test suites
│   ├── domain/                # Domain logic and policy test suite
│   ├── infra/                 # Database and embedding strategy test suite
│   └── services/              # Service and orchestration test suite
├── summary.md                 # Technical architecture & changelog
├── agent.md                   # Agentic pair programming operational rules
├── pyproject.toml             # Project metadata and dependencies
└── requirements.txt           # Python package requirements
```

---

## 🛠️ Technology Stack

- **Language**: Python 3.14+ (or Python 3.10+)
- **Data Validation & Modeling**: [Pydantic v2](https://docs.pydantic.dev/)
- **Database**: [MongoDB Atlas](https://www.mongodb.com/products/platform/atlas-database) (Vector Search & Operational Indexes)
- **Database Driver**: [PyMongo](https://pymongo.readthedocs.io/) ($\ge 4.7$ for automated vector indexing)
- **Generative AI & LLMs**: [Google GenAI SDK](https://github.com/google-gemini/google-genai) (`google-genai`)
- **Embeddings**: [Voyage AI](https://www.voyageai.com/) / MongoDB Automated Embedding
- **User Interface**: [Streamlit](https://streamlit.io/)
- **Testing & Quality Assurance**: [Pytest](https://docs.pytest.org/)

---

## 🗄️ Database Collection Schemas

Memory Chef persists data across three core MongoDB collections within the `chef_pantry` database: `memories`, `messages`, and `users`.

### 1. `memories` Collection
Stores all extracted episodic and semantic culinary memories, preference profiles, allergies, inventory, and meal feedback.

```json
{
  "_id": "67232230113f382103f69910",
  "user_id": "user_123",
  "session_id": "session_abc",
  "type": "allergy",
  "text": "Severe peanut allergy",
  "structured": {
    "allergen": "peanut",
    "severity": "severe",
    "notes": "Anaphylactic reaction to all tree nuts and peanuts"
  },
  "tags": ["allergy", "peanut", "severe"],
  "source": "user",
  "source_message_id": "67232230113f382103f69905",
  "confidence": 1.0,
  "embedding": [0.0125, -0.0431, 0.0892, "... 1024 dimensions ..."],
  "created_at": "2026-10-31T06:30:00Z",
  "updated_at": "2026-10-31T06:30:00Z",
  "last_used_at": "2026-10-31T07:15:00Z",
  "expires_at": null,
  "status": "active",
  "superseded_by": null,
  "supersedes": null,
  "protected": true,
  "use_count": 4,
  "deleted_at": null,
  "visibility": "private"
}
```

#### Field Specifications:
| Field | Type | Description |
|---|---|---|
| `_id` | `ObjectId / string` | Primary unique 24-character hexadecimal identifier. |
| `user_id` | `string` | Identifier of the user who owns this memory. |
| `session_id` | `string \| null` | Chat session identifier in which this memory was established. |
| `type` | `string` | Categorical type: `"allergy"`, `"preference"`, `"meal_outcome"`, `"pantry_item"`, `"temporary_context"`. |
| `text` | `string` | Normalized, clean natural language memory statement. |
| `structured` | `object` | Type-specific structured metadata payload (see sub-schemas below). |
| `tags` | `array<string>` | Normalized, lowercase classification tags. |
| `source` | `string` | Origin of capture: `"user"`, `"agent"`, `"inferred"`, or `"system"`. |
| `source_message_id` | `string \| null` | Pointer to source chat message if extracted from a conversation turn. |
| `confidence` | `double` | Extraction confidence score between `0.0` and `1.0`. |
| `embedding` | `array<double> \| null` | Dense vector embedding (1024 dims for Voyage AI; omitted in Atlas Auto mode). |
| `created_at` | `ISODate (UTC)` | Creation timestamp. |
| `updated_at` | `ISODate (UTC)` | Timestamp of most recent update or modification. |
| `last_used_at` | `ISODate \| null` | Timestamp when this memory was last recalled and cited in an answer. |
| `expires_at` | `ISODate \| null` | Expiration timestamp in UTC (enforces automated TTL eviction). |
| `status` | `string` | Lifecycle state: `"active"`, `"superseded"`, `"deleted"`, or `"expired"`. |
| `superseded_by` | `string \| null` | Pointer to the newer memory ID that replaced this entry. |
| `supersedes` | `string \| null` | Pointer to the older memory ID that this entry replaced. |
| `protected` | `boolean` | If `true`, immune to automatic decay, replacement, or eviction (forced `true` for allergies). |
| `use_count` | `integer` | Cumulative count of times this memory contributed to generation. |
| `deleted_at` | `ISODate \| null` | Timestamp recorded upon soft-deletion. |
| `visibility` | `string` | Sharing scope: `"private"` or `"shared"`. |

#### Structured Payloads by Memory Type:
- **`allergy`**: `{"allergen": str, "severity": "mild"|"moderate"|"severe", "notes": str}`
- **`preference`**: `{"category": str, "target": str, "polarity": "like"|"dislike"|"neutral", "strength": float}`
- **`meal_outcome`**: `{"dish_name": str, "rating": int (1-5), "notes": str, "adjustments": list[str]}`
- **`pantry_item`**: `{"ingredient": str, "quantity": str, "unit": str, "expires_at": datetime}`
- **`temporary_context`**: `{"context": str, "for_people": int}`

#### Operational & Vector Indexes:
- **Vector Search Index**: `memories_vector_index` on `embedding` (or `text` for Atlas Automated Embedding).
- **TTL Index**: `expires_at` ascending with `expireAfterSeconds: 0`.
- **Compound Query Index**: `[("user_id", 1), ("status", 1), ("type", 1)]`.

---

### 2. `messages` Collection
Records user and assistant conversation history, tracking memory utilization and turns.

```json
{
  "_id": "67232230113f382103f69905",
  "user_id": "user_123",
  "session_id": "session_abc",
  "role": "assistant",
  "content": "I recommend a spicy Thai Basil Tofu stir-fry. Because I remembered you have a severe peanut allergy, I ensured no peanuts or peanut oils are used.",
  "memories_used": [
    {
      "memory_id": "67232230113f382103f69910",
      "text": "Severe peanut allergy",
      "type": "allergy",
      "score": 0.95,
      "reasons": ["Always-applied allergy constraint", "High semantic relevance to Thai cuisine"]
    }
  ],
  "memories_created": ["67232230113f382103f69915"],
  "created_at": "2026-10-31T06:30:05Z"
}
```

#### Field Specifications:
| Field | Type | Description |
|---|---|---|
| `_id` | `ObjectId / string` | Primary unique 24-character hexadecimal identifier. |
| `user_id` | `string` | User ID associated with this interaction. |
| `session_id` | `string` | Conversation session grouping handle. |
| `role` | `string` | Message sender role: `"user"` or `"assistant"`. |
| `content` | `string` | Full text content of the message. |
| `memories_used` | `array<object>` | List of recalled memory objects cited during answer generation. |
| `memories_created` | `array<string>` | List of memory IDs extracted and persisted from this turn. |
| `created_at` | `ISODate (UTC)` | UTC timestamp of message creation. |

#### Operational Indexes:
- **Compound History Index**: `[("session_id", 1), ("created_at", 1)]`.

---

### 3. `users` Collection
Stores user account profiles, measurement standards, and privacy settings.

```json
{
  "_id": "67232230113f382103f69900",
  "user_id": "user_123",
  "display_name": "Aaditya",
  "created_at": "2026-10-31T06:00:00Z",
  "settings": {
    "units": "metric",
    "memory_enabled": true
  }
}
```

#### Field Specifications:
| Field | Type | Description |
|---|---|---|
| `_id` | `ObjectId / string` | Primary unique 24-character hexadecimal identifier. |
| `user_id` | `string` | Unique user handle (e.g., `'user_123'`). |
| `display_name` | `string` | User display name. |
| `created_at` | `ISODate (UTC)` | User profile creation timestamp in UTC. |
| `settings.units` | `string` | Preferred recipe measurement units: `'metric'` or `'imperial'`. |
| `settings.memory_enabled`| `boolean` | Master toggle: when `false`, bypasses memory retrieval and storage. |

#### Operational Indexes:
- **Unique Account Index**: `[("user_id", 1)]` (unique: true).

---

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 or newer (tested with Python 3.14)
- A MongoDB Atlas cluster (M0 or higher; M10+ required for Automated Embedding)
- A Google Gemini API Key

### 2. Clone and Setup Environment
```bash
# Clone the repository
git clone https://github.com/Helik8907/Chef-Pantry.git
cd Chef-Pantry

# Create and activate virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On Unix / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and fill in your connection details:
```bash
cp .env.example .env
```

Key environment variables:
| Variable | Default / Example | Purpose |
|---|---|---|
| `MONGO_URI` | `mongodb+srv://...` | MongoDB connection URI |
| `MONGO_PASSWORD` | `...` | MongoDB database user password |
| `MONGO_DB_NAME` | `chef_pantry` | Target MongoDB database name |
| `GEMINI_API_KEY` | `...` | Google Gemini API key |
| `LLM_PROVIDER` | `gemini` | LLM engine (`gemini` or `mock`) |
| `EMBEDDING_MODE` | `mock` | Embedding strategy (`mock`, `auto`, or `self`) |
| `VOYAGE_API_KEY` | `...` | API key for Voyage AI (when using `self` mode) |
| `VECTOR_INDEX_NAME`| `memories_vector_index` | Name of MongoDB vector search index |

### 4. Provision Database Indexes
Ensure your operational and vector search indexes are configured in MongoDB:
```bash
python scripts/create_indexes.py
```

### 5. Running Tests
Run the comprehensive offline test suite:
```bash
pytest
```

---

## 📑 Documentation & Contribution Guidelines

- **Project Summary & Changelog**: Consult [summary.md](summary.md) for architectural records, directory maps, and the historical changelog.
- **Agentic Operational Rules**: Refer to [agent.md](agent.md) for pair programming rules, strict change verification protocols, and documentation synchronization rules.

