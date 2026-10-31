# Chef 🍳

Chef is a personalized culinary assistant built with Streamlit, FastAPI, MongoDB, and Google Gemini. It remembers useful cooking context across conversations and uses it to tailor recipe suggestions.

## Features

- **Conversational cooking help:** Chat across persistent sessions and get exactly three concise recipe options in food and cooking answers.
- **Personal memory:** Extracts and recalls allergies, dietary preferences, likes and dislikes, pantry items, temporary context, and meal feedback.
- **Memory management:** Review, search, filter, add, and forget saved memories from the dedicated Memory Management page.
- **Allergy safeguards:** Allergy memories are protected and always supplied to recipe generation. Deterministic checks flag allergen conflicts and trigger a safety regeneration path.
- **Memory lifecycle:** Deduplicates memories, handles corrections and superseding, supports confirmation for sensitive changes, expires temporary entries, and soft-deletes forgotten items.
- **Relevant recall:** Combines vector retrieval with ranking for semantic relevance, recency, feedback, memory type, and prior use. Dietary preferences are also supplied to Chef even if vector search does not retrieve them.
- **Account and chat API:** Streamlit sign-in and registration UI plus FastAPI routes for authentication, users, and chat.
- **Flexible providers:** Use Google Gemini or a mock LLM, and choose Atlas automated embeddings, Voyage AI client-side embeddings, or deterministic mock embeddings.
- **Privacy-minded memory handling:** Redacts detected secrets before memory storage and scopes memory operations by user.

## Architecture

```text
Streamlit UI ─┐
              ├─ Services ─ Domain rules
FastAPI API ──┘      │
                     ├─ MongoDB repositories and vector search
                     └─ LLM and embedding providers
```

- `app/ui/` — Streamlit chat, authentication, sidebar, and memory management.
- `app/api/` — FastAPI application, dependencies, and route handlers.
- `app/services/` — Chat orchestration, extraction, generation, recall, storage, conflict handling, and lifecycle.
- `app/domain/` — Data models, privacy redaction, memory policies, ranking, and safety rules.
- `app/infra/` — MongoDB access, configuration, LLM and embedding provider integrations.
- `app/prompts/` — Prompts for extraction, answers, conflict checks, and safety regeneration.
- `scripts/` — MongoDB index provisioning and demo utilities.
- `tests/` — Domain, infrastructure, service, and API tests.
- `summary.md` — Detailed architecture, file map, and project changelog.

## Requirements

- Python 3.14 or newer (per `pyproject.toml`)
- MongoDB database and network access configured for this application
- Google Gemini API key when using the Gemini provider
- MongoDB Atlas Vector Search for vector recall; Atlas automated embedding may require a supported Atlas tier
- Voyage AI API key when using client-side (`self`) embeddings

## Setup

1. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   # Windows PowerShell
   .venv\Scripts\Activate.ps1
   # macOS / Linux
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   Alternatively, with `uv`:

   ```bash
   uv sync
   ```

3. Copy `.env.example` to `.env` and set the credentials and provider settings for your environment. At minimum, configure `MONGO_URI`, `MONGO_DB_NAME`, and `GEMINI_API_KEY` when running with Gemini. The application can substitute `MONGO_PASSWORD` for the `<db_password>` placeholder in `MONGO_URI`.

   Important settings:

   | Setting | Purpose |
   | --- | --- |
   | `MONGO_URI` | MongoDB connection string |
   | `MONGO_PASSWORD` | Optional password substituted into the URI placeholder |
   | `MONGO_DB_NAME` | Database name (default: `chef_pantry`) |
   | `GEMINI_API_KEY` | Google Gemini API credential |
   | `MODEL` | Gemini model used by extraction and answer generation |
   | `LLM_PROVIDER` | `gemini` or `mock` |
   | `EMBEDDING_MODE` | `mock`, `auto`, or `self` |
   | `EMBEDDING_MODEL` | Voyage embedding model for embedding modes that use it |
   | `VOYAGE_API_KEY` | Credential for `self` embedding mode |
   | `VECTOR_INDEX_NAME` | MongoDB vector index name |
   | `VECTOR_TEXT_PATH` | Text field used by Atlas automated embedding |

4. Provision the MongoDB operational and vector search indexes:

   ```bash
   python scripts/create_indexes.py
   ```

   Configure the Atlas vector index and embedding mode to match each other before using vector recall.

## Run the application

Start the Streamlit application:

```bash
streamlit run app/ui/main.py
```

To run the FastAPI backend separately:

```bash
uvicorn app.api.main:app --reload
```

The API's interactive documentation is available at `/docs` while the server is running. Its health endpoint is `/api/health`.

## Tests

Run the test suite from the project root:

```bash
pytest
```

Mock LLM and embedding providers support offline development and unit testing. Database-backed vector search and the connected Gemini/Voyage services still require their configured external services.

## Project documentation

- [Project summary and changelog](summary.md)
- [Agent operating rules](Agent.md)
