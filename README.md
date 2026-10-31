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
│       ├── components/        # Reusable chat and memory visualizer panels
│       ├── pages/             # Memory inspector and debug pages
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

