# CLAUDE.md - Scrappy Recipes Context & Roadmap

## 1. Project Overview & Architecture
Scrappy Recipes is an AI-powered recipe extraction and semantic search service built with FastAPI, PostgreSQL + pgvector, and LLMs (OpenAI & Gemini).

* **Backend Framework:** FastAPI (Async)
* **Database & Vector Store:** PostgreSQL with `pgvector` extension (Dockerized)
* **ORM & Migrations:** Async SQLAlchemy 2.0 + Alembic
* **LLMs & Embeddings:**
  * OpenAI `text-embedding-3-small` (1536 dims) for vector search embeddings — `app/services/embedding_service.py`
  * OpenAI `gpt-4o-mini` for text recipe parsing — `app/services/llm_parser.py`
  * Gemini `gemini-3.5-flash` for vision/multimodal image parsing — `app/services/llm_parser.py`
    (verified working 2026-08-09)
* **Containerisation:** Docker Compose (`scrappy_recipes_app`, `scrappy_recipes_db`)

---

## 2. Essential Commands

### Development & Docker
* **Start/Rebuild Stack:** `docker compose up -d --build`
* **View Live App Logs:** `docker compose logs -f app`
* **Stop Containers:** `docker compose down`
* **Check Status:** `docker compose ps`

### Database Operations & Migrations
* **Run Alembic Migrations:** `docker compose exec app alembic upgrade head`
* **Generate New Migration:** `docker compose exec app alembic revision --autogenerate -m "description"`
* **Direct PSQL Access:** `docker exec -it scrappy_recipes_db psql -U recipe_admin -d scrappy_recipes`
  * User comes from `POSTGRES_USER` in `.env` (currently `recipe_admin`).

### Testing
`tests/` is a **pytest suite with every LLM and HTTP call mocked** — it needs no API keys, makes
no network requests, and costs nothing. 40 tests, ~1.3s.

* **Run everything:** `venv/bin/python -m pytest`
* **One file:** `venv/bin/python -m pytest tests/test_router.py`
* **One test:** `venv/bin/python -m pytest tests/test_scraper.py -k timeout`
* **Verbose:** `venv/bin/python -m pytest -v`
* **In the container:** `docker compose exec app python -m pytest`
  * Needs a rebuild first: `docker compose up -d --build`.

Config lives in `pytest.ini` (`asyncio_mode = auto`, so `async def` tests need no decorator).

**Where the mocks attach** — patch at these boundaries, not at the service methods, so the real
parsing/cleaning logic stays under test:

| Seam | Fixture (`tests/conftest.py`) |
| --- | --- |
| `openai_client.beta.chat.completions.parse` | `mock_openai_parse` (sync `MagicMock`, not async) |
| `gemini_client.models.generate_content` | `mock_gemini_generate` (returns JSON *string*) |
| `httpx.AsyncClient` | `httpx.MockTransport` in `tests/test_scraper.py` |
| `AsyncOpenAI` (embeddings) | patched in `tests/test_persistence.py` |
| `AsyncSession` | `mock_db_session` (`add` sync; `commit`/`refresh` async) |

An autouse `_no_live_api` fixture overwrites both API keys with dummies, so a missing mock fails
loudly on a stub instead of quietly billing a real request.

**Live API checks** — `tests/live/check_*.py` still exercise the real APIs for credential/billing
/model verification. They are excluded from collection by name and by `norecursedirs`. See
`tests/live/README.md`.

---

## 3. Key Directory Structure
```text
.
├── app/
│   ├── database.py                 # Async DB engine & session dependency
│   ├── main.py                     # FastAPI entry point, lifespan, routes
│   ├── models.py                   # SQLAlchemy RecipeModel (includes Vector column)
│   ├── schemas.py                  # Pydantic schemas (RecipeRead, ParseTextRequest, etc.)
│   └── services/
│       ├── embedding_service.py    # generate_embedding() — OpenAI text-embedding-3-small
│       ├── llm_parser.py           # RecipeParserService: text (OpenAI) + image (Gemini) parsing
│       ├── recipe_db_service.py    # Recipe persistence helpers
│       ├── router_service.py       # LLMRouterService for text, url, image routing
│       └── scraper_service.py      # URL fetching & HTML extraction
├── tests/                          # Mocked pytest suite — no API keys, no network
│   ├── conftest.py                 # Fixtures: stubbed LLM clients, sample recipe, DB double
│   ├── test_api.py                 # Endpoint contracts: draft → confirm, error mapping
│   ├── test_parsers.py             # RecipeParserService (OpenAI + Gemini routes)
│   ├── test_router.py              # Route selection, precedence, parse-only guarantee
│   ├── test_scraper.py             # HTML cleaning + network failures via MockTransport
│   ├── test_persistence.py         # Embedding text/vector + DB save
│   ├── live/                       # Opt-in real-API checks (not collected by pytest)
│   │   ├── README.md
│   │   ├── check_parsers.py
│   │   ├── check_router.py
│   │   └── check_scraper.py
│   └── test_images/                # Multi-page recipe screenshot fixtures
│       ├── recipe_page1.jpeg
│       └── recipe_page2.jpeg
├── alembic/                        # DB migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── alembic.ini
├── pytest.ini                      # asyncio_mode=auto, strict markers, live/ excluded
├── manage_db.py                    # DB initialization / --migrate script
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
└── CLAUDE.md
```

---

## 4. Completed Capabilities (Current State)
- [x] Docker setup running PostgreSQL with pgvector enabled automatically.
- [x] Health check endpoint: `GET /health`.
- [x] **Two-step draft → confirm ingestion flow** (see below).
- [x] Embedding generation at confirm time — drafts the user discards cost nothing.
- [x] Basic vector similarity search endpoint: `GET /api/v1/recipes/search`.
- [x] Mocked pytest suite covering services *and* API routes.

### The draft → confirm flow
Parsing and persistence are deliberately separate. Parse endpoints are **read-only**: they return
an unsaved `RecipeCreate` draft and never touch Postgres. The client reviews (and may correct) the
draft, then POSTs it to `/confirm`, which is the **only** write path for new recipes.

```text
POST /api/v1/recipes/parse-text     ┐
POST /api/v1/recipes/parse-url      ├─→ 200 OK, RecipeCreate draft (no id, no DB write)
POST /api/v1/recipes/parse-images   ┘
                                          │  client reviews / edits
                                          ▼
POST /api/v1/recipes/confirm        ──→ 201 CREATED, RecipeRead (id assigned, embedding stored)
```

No draft state is held server-side — the client echoes the full (possibly edited) recipe back, so
whatever it submits is what gets stored. There is no draft TTL, no eviction, and nothing to lose
on restart or across multiple workers.

| Endpoint | Method | Status | Body → Response | Writes? |
| --- | --- | --- | --- | --- |
| `/api/v1/recipes/parse-text` | POST | 200 | `ParseTextRequest` → `RecipeCreate` | no |
| `/api/v1/recipes/parse-url` | POST | 200 | `ParseUrlRequest` → `RecipeCreate` | no |
| `/api/v1/recipes/parse-images` | POST | 200 | multipart `files[]` → `RecipeCreate` | no |
| `/api/v1/recipes/confirm` | POST | 201 | `RecipeCreate` → `RecipeRead` | **yes** |
| `/api/v1/recipes/search` | GET | 200 | `?q=&limit=` → `List[RecipeRead]` | no |
| `/health` | GET | 200 | — | no |

`RecipeRead` does not expose the `embedding` column: it is 1536 floats (~25KB of JSON) per row,
no client consumes it, and it multiplied `/search` payloads by ~25x.

---

## 5. Known Issues
- **`app/schemas.py`** uses the Pydantic v1 `class Config` style on `RecipeRead` — deprecated, and
  slated for removal in Pydantic v3. Replace with `model_config = ConfigDict(from_attributes=True)`.
- **`/confirm` has no duplicate detection.** Submitting the same draft twice creates two rows.
- **`docker-compose.yml`** still declares `version: '3.8'`, which modern Compose ignores with a
  warning on every command.

---

## 6. Environment Variables
`.env` at the repo root supplies all of these; `docker-compose.yml` interpolates from it.

| Variable | Used by | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | embeddings + text parsing | Forwarded to the `app` container |
| `GEMINI_API_KEY` | image/vision parsing | Forwarded to the `app` container |
| `POSTGRES_USER` | db + connection strings | Currently `recipe_admin` |
| `POSTGRES_PASSWORD` | db + connection strings | Falls back to a default if unset |
