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
* **Web Search Fallback:** DuckDuckGo via `ddgs` (`DDGS().text(...)`) — `app/services/web_search_service.py`
* **UI:** Streamlit single-page app — `ui/app.py` (talks to the API over HTTP, no direct DB access)
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
no network requests, and costs nothing. 81 tests, ~3s.

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
| `AsyncSession` | `mock_db_session` (`add` sync; `commit`/`refresh`/`get`/`delete` async) |

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
│   ├── models.py                   # SQLAlchemy RecipeModel (includes Vector column), MenuModel
│   ├── schemas.py                  # Pydantic schemas (RecipeRead, ParseTextRequest, etc.)
│   └── services/
│       ├── embedding_service.py    # generate_embedding() — OpenAI text-embedding-3-small
│       ├── llm_parser.py           # RecipeParserService: text (OpenAI) + image (Gemini) parsing
│       ├── recipe_db_service.py    # Recipe persistence helpers (save + delete)
│       ├── router_service.py       # LLMRouterService for text, url, image routing
│       ├── scraper_service.py      # URL fetching & HTML extraction
│       └── web_search_service.py   # search_recipes_web() — DuckDuckGo (ddgs) top-3 lookup
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
├── ui/
│   └── app.py                      # Streamlit UI: Ingestion, Search, Meal Plan tabs
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
- [x] Vector similarity search endpoint: `GET /api/v1/recipes/search`, returns cosine distance
  alongside each hit (see below).
- [x] Delete endpoint: `DELETE /api/v1/recipes/{recipe_id}` (see below).
- [x] Web search fallback endpoint: `GET /api/v1/recipes/search-web` (see below).
- [x] Paginated library listing endpoint: `GET /api/v1/recipes` (see below).
- [x] Mocked pytest suite covering services *and* API routes.
- [x] Streamlit UI Tab 1 (Ingestion): parse-from-URL/text/images → review draft → confirm.
- [x] Streamlit UI Tab 2 (Search & Discovery), including a "Browse All Recipes" library view
  (see below).
- [x] `MenuModel` and `RecipeModel.last_menu_number` (migration `d5f0ee3eb3ce`) — data model only,
  no API/UI yet (see below).

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
| `/api/v1/recipes/search` | GET | 200 | `?q=&limit=` → `List[RecipeSearchResult]` | no |
| `/api/v1/recipes/search-web` | GET | 200 | `?query=` → `List[WebSearchResult]` | no |
| `/api/v1/recipes` | GET | 200 | `?skip=&limit=` → `RecipeListResponse` | no |
| `/api/v1/recipes/{recipe_id}` | DELETE | 204 / 404 | — → no body | **yes** (delete) |
| `/health` | GET | 200 | — | no |

`RecipeRead` does not expose the `embedding` column: it is 1536 floats (~25KB of JSON) per row,
no client consumes it, and it multiplied `/search` payloads by ~25x. `RecipeSearchResult` (used
only by `/search`) is `RecipeRead` plus a `distance: float` field — pgvector's cosine distance
(`<=>`) between the query embedding and that row, `0` = identical, `2` = opposite. Lower is closer.

### Delete flow
`DELETE /api/v1/recipes/{recipe_id}` looks the row up with `AsyncSession.get`, deletes it, and
commits — implemented in `RecipeDatabaseService.delete_recipe` (`app/services/recipe_db_service.py`).
Returns `204 No Content` when a row was removed, `404` when no recipe with that id exists, and
`500` on an unexpected DB failure. There is no soft-delete or cascade behavior; the row and its
embedding are removed permanently.

### Web search fallback
`GET /api/v1/recipes/search-web?query=...` is for when the user has no URL or pasted text to feed
`parse-url` / `parse-text` yet — e.g. "find me a recipe for X" — and needs candidate pages to pick
from first. It searches the public web (DuckDuckGo, via the `ddgs` package) and returns the top 3
matches as `[{"title": "...", "url": "...", "snippet": "..."}]`. Before querying, it appends
`recipe cooking` to the user's search string (e.g. `fish dish` → `fish dish recipe cooking`) to
steer DuckDuckGo toward actual cooking pages instead of Wikipedia/medical results. It only
surfaces candidates; it does not parse or persist anything — the client still has to send a
chosen URL through `parse-url` → `confirm`. `400` on an empty query, `500` if the search itself
fails. Implemented in `search_recipes_web()` (`app/services/web_search_service.py`).

### Library listing endpoint
`GET /api/v1/recipes?skip=&limit=` browses the full saved library, newest first, for when the user
isn't searching for anything specific yet. `skip` defaults to `0`, `limit` defaults to `20` (max
`100`). Implemented in `RecipeDatabaseService.list_recipes` (`app/services/recipe_db_service.py`),
which runs a `SELECT count(*)` alongside the paginated `ORDER BY created_at DESC` query so the
response can report the total row count without a second round trip from the client. Returns a
`RecipeListResponse`: `{"items": [RecipeRead], "total": int, "page": int, "limit": int}`, where
`page` is derived as `(skip // limit) + 1`. `500` on an unexpected DB failure; no `404` case since
an out-of-range `skip` just yields an empty `items` list. Sorting relies on the `created_at`
column added to `RecipeModel` (migration `fe8e517ee849`) — every prior row was backfilled to the
migration's `now()` at the time it ran, so their relative order among each other is undefined,
but any row inserted after `confirm` sorts correctly.

### Search UI (Tab 2) — `ui/app.py`, `search_tab`
Ties `/search`, `/search-web`, and `DELETE /{recipe_id}` together into one flow. There is no hard
distance cutoff that hides the local result — every search renders a consistent outcome:

1. User types a query and clicks **Search Local Recipes** → calls `/search` with `limit=1`.
2. **A result came back:** always renders the top hit — regardless of how distant a match it is —
   via `Distance: <d> | Match Quality: <label>` (`match_quality_label()`: `≤0.3` Excellent,
   `≤0.45` Good, `≤0.6` Moderate, else Weak), the full recipe (via the same `render_draft_preview`
   used by the ingestion tab), and a **Delete Recipe** button wired to
   `DELETE /api/v1/recipes/{recipe_id}`.
3. **No rows in the database at all:** shows an info message instead of a recipe card.
4. **Always, right after either outcome:** a **"Not what you were looking for?"** section with a
   **Search Web for this Query** button → calls `/search-web` and lists the top 3 hits, each with
   a **Parse this Recipe** button. This no longer depends on the local match being poor — it's
   offered unconditionally once a local search has run.

Clicking **Parse this Recipe** doesn't parse in place — it stages the URL in
`st.session_state["pending_recipe_url"]` and reruns the script. A check at the top of `ui/app.py`
(before the Ingestion tab's URL `text_input` is instantiated) applies that staged value to the
widget's own state key. This two-step handoff is required because Streamlit raises
`StreamlitAPIException` if you assign to a widget's session-state key after that widget has already
been instantiated in the same script run — and the Ingestion tab renders before the Search tab.

Beneath all of the above, a permanent **"Browse All Recipes"** section calls `GET /api/v1/recipes`
independently of whether a search has run — it is not gated behind the search flow. Pagination is
tracked in `st.session_state["browse_page"]` (0-indexed) and sent to the API as `skip = page *
20`, `limit = 20`. Each recipe renders as a bordered card: title, cook time, an
**"Ingredients & Instructions"** expander (reusing `render_draft_preview`), and its own **Delete
Recipe** button wired to `DELETE /api/v1/recipes/{recipe_id}` — deleting rerenders in place rather
than touching `local_search_result`. **Previous Page** / **Next Page** buttons increment or
decrement `browse_page` and are disabled at the first/last page respectively (last page computed
client-side from the response's `total`).

### Meal menu data model (no API/UI yet)
`RecipeModel` gained a nullable `last_menu_number: int` column, and a new `MenuModel` table
(`menus`) tracks generated meal menus: `id`, a unique/indexed sequential `menu_number` (1, 2, 3...),
`created_at`, and `recipe_ids` (`JSON`, a plain list of recipe ids — matches the existing
`ingredients`/`instructions`/`tags` convention on `RecipeModel` rather than a Postgres `ARRAY`).
Added in migration `d5f0ee3eb3ce` (`alembic/versions/d5f0ee3eb3ce_*.py`), applied to the dev DB.
Nothing populates `last_menu_number` or writes to `menus` yet — no service, endpoint, or schema
exists for menu generation; this is purely the schema groundwork for that feature.

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
