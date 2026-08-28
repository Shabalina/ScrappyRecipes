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
* **Auth:** Shared `X-API-Key` header, checked against `APP_API_KEY` — `app/core/security.py`
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
no network requests, and costs nothing. 136 tests, ~3s.

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
| `AsyncSession` | `mock_db_session` (`add` sync; `commit`/`refresh`/`get`/`delete`/`execute`/`scalar` async) |

An autouse `_no_live_api` fixture overwrites both LLM API keys with dummies and pins `APP_API_KEY`
to `TEST_API_KEY` (`tests/conftest.py`), so a missing mock fails loudly on a stub instead of
quietly billing a real request. Every `TestClient` in the suite is constructed with
`headers=API_KEY_HEADERS` (also `tests/conftest.py`) so existing tests pass through the auth
dependency without each one wiring a header by hand.

**Live API checks** — `tests/live/check_*.py` still exercise the real APIs for credential/billing
/model verification. They are excluded from collection by name and by `norecursedirs`. See
`tests/live/README.md`.

---

## 3. Key Directory Structure
```text
.
├── app/
│   ├── core/
│   │   └── security.py             # verify_api_key() — X-API-Key header check against APP_API_KEY
│   ├── database.py                 # Async DB engine & session dependency
│   ├── main.py                     # FastAPI entry point, lifespan, routes
│   ├── models.py                   # SQLAlchemy RecipeModel (includes Vector column), MenuModel
│   ├── schemas.py                  # Pydantic schemas (RecipeRead, ParseTextRequest, etc.)
│   └── services/
│       ├── embedding_service.py    # generate_embedding() — OpenAI text-embedding-3-small
│       ├── llm_parser.py           # RecipeParserService: text (OpenAI) + image (Gemini) parsing,
│                                    # + generate_shopping_list() (OpenAI) for menu aggregation
│       ├── menu_service.py         # get_slot_candidates() — scored recipe candidates for a menu slot
│       ├── recipe_db_service.py    # Recipe persistence helpers (save + delete)
│       ├── router_service.py       # LLMRouterService for text, url, image routing
│       ├── scraper_service.py      # URL fetching & HTML extraction
│       ├── shopping_service.py     # generate_menu_shopping_list() — cached, LLM-aggregated shopping list
│       └── web_search_service.py   # search_recipes_web() — DuckDuckGo (ddgs) top-3 lookup
│   └── routers/
│       └── menu.py                 # Menu endpoints: slot-candidates (read-only), confirm (write),
│                                    # menu history + shopping-list (read-only, on the /api/v1/menus router)
├── tests/                          # Mocked pytest suite — no API keys, no network
│   ├── conftest.py                 # Fixtures: stubbed LLM clients, sample recipe, DB double
│   ├── test_api.py                 # Endpoint contracts: draft → confirm, error mapping
│   ├── test_parsers.py             # RecipeParserService (OpenAI + Gemini routes)
│   ├── test_router.py              # Route selection, precedence, parse-only guarantee
│   ├── test_scraper.py             # HTML cleaning + network failures via MockTransport
│   ├── test_persistence.py         # Embedding text/vector + DB save
│   ├── test_menu_service.py        # Slot candidate scoring: exclusion, variety penalty, expiry
│   ├── test_menu_router.py         # Menu endpoint contracts: slot-candidates, confirm
│   ├── test_shopping_service.py    # Shopping list generation + caching, and its endpoint
│   ├── test_security.py            # X-API-Key gate: /health public, /api/v1/... 403/200 cases
│   ├── live/                       # Opt-in real-API checks (not collected by pytest)
│   │   ├── README.md
│   │   ├── check_parsers.py
│   │   ├── check_router.py
│   │   └── check_scraper.py
│   └── test_images/                # Multi-page recipe screenshot fixtures
│       ├── recipe_page1.jpeg
│       └── recipe_page2.jpeg
├── ui/
│   └── app.py                      # Streamlit UI: Parse Recipe, Search & Browse, Menu Builder,
│                                    # Existing Menus tabs
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
- [x] `MenuModel` and `RecipeModel.last_menu_number` (migration `d5f0ee3eb3ce`) — data model
  (see below).
- [x] `get_slot_candidates()` menu slot candidate scoring service (see below).
- [x] Menu API endpoints: `GET /api/v1/menu/slot-candidates`, `POST /api/v1/menu/confirm`
  (`app/routers/menu.py`) (see below).
- [x] Streamlit UI Tab 3 (Meal Plan): builds a 1–6 meal weekly menu slot-by-slot and confirms it
  (see below).
- [x] `MenuModel.shopping_list` column (migration `8e1ad5807d15`) and `GET /api/v1/menus` menu
  history endpoint (see below).
- [x] Shopping list aggregation: `generate_menu_shopping_list()` and
  `GET /api/v1/menus/{menu_id}/shopping-list` (see below).
- [x] Streamlit UI Tab 4 (Existing Menus): browse saved menus, highlight the active one, and view
  each one's shopping list in a modal dialog (see below).
- [x] API key authentication on every `/api/v1/...` route, `/health` left public (see below).

### API key authentication
Every route under `/api/v1/...` requires an `X-API-Key` header matching `APP_API_KEY`; `/health`
is intentionally exempt since container health probes can't carry a secret. Enforced by
`verify_api_key()` (`app/core/security.py`, `fastapi.security.APIKeyHeader(auto_error=False)`),
attached as a `Depends()` — per-route on the bare `@app.get/post/delete` endpoints in `main.py`,
and once at the `APIRouter(dependencies=[...])` level for `router`/`history_router` in
`app/routers/menu.py`, rather than globally on the `FastAPI()` app (which would also gate
`/health`). A missing or wrong key is `403 Forbidden` with `{"detail": "Invalid or missing API
key"}`. The key is read from `os.environ` inside the dependency (not frozen as a module constant
at import time) so tests can override it per-run via `monkeypatch.setenv`; it defaults to
`local_dev_secret_key_123` when unset. The Streamlit UI sends it on every request via a shared
`requests.Session()` (`ui/app.py`, `api_session`) seeded from `st.secrets.get("APP_API_KEY", ...)`
falling back to the `APP_API_KEY` env var, then the same default. `show_api_error()` in `ui/app.py`
special-cases a `403` response into "Authentication failed: Invalid API Key" instead of the
generic error path.

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
| `/api/v1/menu/slot-candidates` | GET | 200 | `?q=&exclude_ids=&limit=` → `List[SlotCandidateRead]` | no |
| `/api/v1/menu/confirm` | POST | 201 | `MenuConfirmRequest` → `MenuRead` | **yes** |
| `/api/v1/menus` | GET | 200 | `?limit=&skip=` → `List[MenuHistoryRead]` | no |
| `/api/v1/menus/{menu_id}/shopping-list` | GET | 200 / 404 | — → `ShoppingListResult` | **yes** (cache only, on first call) |
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

### Meal menu data model
`RecipeModel` gained a nullable `last_menu_number: int` column, and a new `MenuModel` table
(`menus`) tracks generated meal menus: `id`, a unique/indexed sequential `menu_number` (1, 2, 3...),
`created_at`, and `recipe_ids` (`JSON`, a plain list of recipe ids — matches the existing
`ingredients`/`instructions`/`tags` convention on `RecipeModel` rather than a Postgres `ARRAY`).
Added in migration `d5f0ee3eb3ce` (`alembic/versions/d5f0ee3eb3ce_*.py`), applied to the dev DB.
`last_menu_number` and `menus` are now populated by `POST /api/v1/menu/confirm` (see below), driven
by the Meal Plan UI tab (see below).

`MenuModel` also has a nullable `shopping_list: JSON` column, added in migration `8e1ad5807d15`
(`alembic/versions/8e1ad5807d15_*.py`). `POST /api/v1/menu/confirm` always inserts `NULL` — it is
populated lazily, on first request, by `generate_menu_shopping_list()` (see below).

### Menu slot candidate scoring — `get_slot_candidates()`
`app/services/menu_service.py` picks recipe candidates for a single slot in a generated menu. It
combines pgvector semantic similarity with a "variety" penalty so a rotation doesn't keep
resurfacing the same dishes:

1. **Vector search.** Embeds the slot `query` and orders recipes by pgvector cosine distance,
   dropping any id in `exclude_ids` (recipes already placed in another slot of this menu) from the
   `WHERE` clause entirely — they're never scored, just absent. The initial pool pulled from the DB
   is `limit * 5` (`CANDIDATE_POOL_MULTIPLIER`), wider than the final `limit`, so recipes demoted by
   the freshness penalty still have lower-ranked-by-distance alternatives to lose to.
2. **Freshness window.** `W = max(1, N // 12)` where `N` is the total recipe count (`floor(N/6/2)`
   collapses to `N // 12` for integer `N`) — bigger libraries get a longer cooldown before a recipe
   is eligible to resurface. `M` is the current max `menu_number` from `menus` (`0` if none exist
   yet).
3. **Penalty.** For a candidate with `last_menu_number` set, `E = M - last_menu_number`. If
   `1 <= E <= W`, penalty `= 0.25 * (W - E + 1) / W` (`VARIETY_PENALTY_ALPHA = 0.25`) — linear
   decay from `0.25` (cooked in the immediately preceding menu) down toward `0` at the window edge.
   Recipes never used, or used further back than `W` menus ago, get `0.0` penalty — no partial
   credit outside the window.
4. **Final score** `= cosine distance + penalty`, ascending (lower wins). Candidates are re-sorted
   by this score and truncated to `limit`.

Returns a list of `SlotCandidate` dataclasses (`recipe: RecipeModel`, `distance: float`,
`penalty: float`, `final_score: float`). `GET /api/v1/menu/slot-candidates` (below) wraps each one
in `SlotCandidateRead` (`recipe: RecipeRead`) for the API boundary. Covered by
`tests/test_menu_service.py` (exclusion via inspecting the compiled `NOT IN` clause params, penalty
demotion changing rank order, and expired/never-used penalties being exactly `0.0`). The
per-slot-to-full-menu orchestration (looping this call once per slot, excluding ids already
placed) lives client-side in the Meal Plan UI tab (see below), not in this service.

### Menu API endpoints — `app/routers/menu.py`
Mirrors the recipe draft → confirm split: `slot-candidates` is read-only, `confirm` is the only
write path for menus.

* **`GET /api/v1/menu/slot-candidates?q=&exclude_ids=&limit=`** — thin wrapper around
  `get_slot_candidates()`. `q` is required and 400s if blank after stripping. `exclude_ids` is an
  optional comma-separated string (e.g. `1,2,3`), parsed to `List[int]`; a malformed value (e.g.
  `1,abc,3`) is a `400`, not a `422`, since it's a hand-parsed query param rather than a
  Pydantic-validated one. `limit` defaults to `3`, bounded `1–6` to match a menu's max slot count.
  Returns `List[SlotCandidateRead]`; `500` on an unexpected failure (e.g. the embedding call).
* **`POST /api/v1/menu/confirm`** — body is `MenuConfirmRequest` (`recipe_ids: List[int]`,
  length `1–6`). Looks up `max(menu_number)` from `menus` (`0` if the table is empty), sets
  `new_menu_number = max + 1`, inserts a `MenuModel` row with that number and the given
  `recipe_ids`, and bulk-`UPDATE`s `last_menu_number = new_menu_number` on every `RecipeModel` row
  whose id is in the list — so the next `slot-candidates` call for a future menu applies the
  variety penalty against this one. No existence check on `recipe_ids`: ids that don't match any
  row are silently no-ops in the `UPDATE`. Returns `201` with `MenuRead`; `500` on an unexpected DB
  failure.

Covered by `tests/test_menu_router.py` — both endpoints through `TestClient` with `get_db`
overridden and `get_slot_candidates` stubbed, following the pattern in `tests/test_api.py`.

### Menu history endpoint — `GET /api/v1/menus`
Lives in `app/routers/menu.py` but on its own `APIRouter` (`history_router`, prefix
`/api/v1/menus`, plural) rather than `router` (prefix `/api/v1/menu`, singular) — both are
included separately in `app/main.py`. Read-only: lists confirmed menus newest-first
(`ORDER BY menu_number DESC`), paginated via `limit` (default `10`, `1–100`) and `skip` (default
`0`). For each menu it resolves `recipe_ids` to full recipe metadata (`id`, `title`,
`cook_time_minutes`) via a second query batched across every menu on the page (one `WHERE id IN
(...)`, not one query per menu), returned as `MenuHistoryRead.recipes` in `recipe_ids` order. An
id that no longer resolves to a row (the recipe was deleted after the menu was confirmed) is
silently dropped from `recipes` rather than erroring. `500` on an unexpected DB failure.

### Shopping list aggregation — `generate_menu_shopping_list()`
`app/services/shopping_service.py` turns a confirmed menu's recipes into one consolidated,
categorized grocery list, exposed via `GET /api/v1/menus/{menu_id}/shopping-list`
(`app/routers/menu.py`, on `history_router`).

1. **Cache check.** Looks the menu up with `AsyncSession.get`; a missing menu returns `None`
   (mapped to `404` by the router). If `menu.shopping_list` is already populated, it's returned
   immediately — no LLM call, no write.
2. **Collect ingredients.** Otherwise queries every `RecipeModel` in `menu.recipe_ids` (one
   `WHERE id IN (...)`), reorders the results back into `recipe_ids` order, and silently drops any
   id that no longer resolves to a row — the same "deleted after the menu was confirmed" tolerance
   as `GET /api/v1/menus`.
3. **LLM consolidation.** `RecipeParserService.generate_shopping_list()` (`app/services/llm_parser.py`,
   OpenAI `gpt-4o-mini` via `beta.chat.completions.parse`, mirroring `parse_text_recipe`) is given
   every recipe's title and ingredients and asked to merge identical/equivalent items into one
   entry with a combined quantity, and group them into grocery sections (Produce, Meat & Seafood,
   Dairy & Refrigerated, Bakery, Pantry & Spices, Other). Structured output is `ShoppingListResult`
   (`app/schemas.py`): `{"categories": [{"category": str, "items": [{"item", "quantity", "unit",
   "sources": [recipe titles]}]}]}`.
4. **Persist.** The result is written to `menu.shopping_list` and committed — every later request
   for the same `menu_id` hits the cache from step 1.

`generate_menu_shopping_list(db, menu_id, parser=None)` accepts an optional `RecipeParserService`
for injection (tests pass a stub); the router and production code leave it `None` and a real
service is constructed on demand — only when generation is actually needed, not on every request.
`500` on an unexpected failure (DB or LLM). Covered by `tests/test_shopping_service.py`: cache
hit/miss at the service level (asserting the LLM is *not* called on a hit), recipe ordering and
deleted-recipe tolerance, and the endpoint's 200/404/500 contract via `TestClient` with
`generate_menu_shopping_list` stubbed.

### The four UI tabs
`ui/app.py` renders four top-level tabs, in this order: **Parse Recipe** (ingestion, the code's
`ingestion_tab`), **Search & Browse** (`search_tab`), **Menu Builder** (`meal_plan_tab`), and
**Existing Menus** (`existing_menus_tab`). The variable names predate this renaming and were left
as-is to avoid a churny rename across the whole file; the tab *labels* are what changed.

### Meal Plan UI (Tab 3, "Menu Builder") — `ui/app.py`, `meal_plan_tab`
Builds a 1–6 meal weekly menu one slot at a time and confirms it via `/api/v1/menu/confirm`. All
state lives in `st.session_state["menu_draft"]` (the list of chosen `RecipeRead` dicts, in pick
order) and `st.session_state["menu_finalizing"]` (`bool`).

* **Selection mode** — shown while `len(menu_draft) < 6` and not finalizing. Header reads
  `Choose Meal {len(menu_draft) + 1} of 6`. A text input + **Find Candidates** button calls
  `GET /api/v1/menu/slot-candidates` with `q=<slot description>` and `exclude_ids` set to the ids
  already in `menu_draft`, so a recipe can't be suggested twice for the same menu. Each of the
  (up to 3) results renders title, cook time, and `final_score`, with a **+ Add to Menu** button
  that appends `candidate["recipe"]` to `menu_draft` and reruns. Next to the slot input, a
  **Finish Menu Early** button (disabled until at least 1 meal is picked) sets `menu_finalizing =
  True` and reruns, dropping straight to the review screen regardless of how few meals were
  chosen. Beneath the candidates, the same paginated library browse as the Search tab (own
  `menu_browse_page` state, so it doesn't fight over pagination with the Search tab's browse) lets
  the user add any saved recipe manually instead of describing a slot; recipes already in the
  draft show "Already in this menu." instead of an Add button rather than being excluded from the
  list.
* **Review mode** — shown once 6 meals are picked, or after Finish Early. Lists every chosen
  recipe with a **Remove** button; removing one pops it from `menu_draft` and always resets
  `menu_finalizing = False`, so removal drops back to selection mode (`Choose Meal N of 6`) even if
  the review screen was reached via Finish Early. A **Confirm & Lock Menu** button POSTs
  `{"recipe_ids": [...]}` to `/api/v1/menu/confirm`; on success it shows the assigned
  `menu_number`, clears `menu_draft`/`menu_finalizing`, and reruns back to an empty selection
  screen for the next menu.

### Existing Menus UI (Tab 4) — `ui/app.py`, `existing_menus_tab`
Read-only browsing of confirmed menus, backed entirely by `GET /api/v1/menus` (fetched with
`limit=100` — no pagination controls, since a household isn't expected to accumulate more menus
than that) and `GET /api/v1/menus/{menu_id}/shopping-list`. No client-side state persists across
reruns beyond what those two calls return each time.

* **Empty state** — if `GET /api/v1/menus` returns `[]`, shows an info message: "No saved menus
  found. Create one in the Menu Builder tab."
* **Listing** — menus are sorted client-side by `menu_number` descending (the API already returns
  them in that order, but the UI re-sorts defensively rather than trusting response order). The
  menu with the highest `menu_number` gets a "🟢 Active Current Menu" badge above its header.
  Each menu renders in a bordered container: `Menu #{menu_number} — Saved on {created_at[:10]}`,
  then every recipe as `- {title} ({cook_time_minutes} min)`.
* **Shopping list dialog** — each card has a `View Shopping List` button. Because `st.dialog`'s
  title is fixed at decoration time, `open_shopping_list_dialog(menu_id, menu_number)` defines and
  immediately invokes a freshly decorated `@st.dialog(f"Shopping List - Menu #{menu_number}")`
  function per click, rather than one dialog function decorated once at module load — that's what
  lets the title carry the specific menu number. Inside, it calls the shopping-list endpoint with
  a spinner (first call per menu is slower — that's the LLM aggregation call described above;
  later opens hit the cached column), then renders items grouped by category with quantity/unit/
  name and a `(from: ...)` caption listing source recipe titles. A trailing `st.code` block
  reflows the same categories/items into plain text for pasting into a phone notes app.

---

## 5. Known Issues
- **`app/schemas.py`** uses the Pydantic v1 `class Config` style on `RecipeRead` — deprecated, and
  slated for removal in Pydantic v3. Replace with `model_config = ConfigDict(from_attributes=True)`.
- **`/confirm` has no duplicate detection.** Submitting the same draft twice creates two rows.
- **`APP_API_KEY` is a single shared secret**, not per-user credentials — there is no user model,
  so revoking access for one caller means rotating the key for everyone.

---

## 6. Environment Variables
`.env` at the repo root supplies all of these; `docker-compose.yml` interpolates from it.

| Variable | Used by | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | embeddings + text parsing | Forwarded to the `app` container |
| `GEMINI_API_KEY` | image/vision parsing | Forwarded to the `app` container |
| `POSTGRES_USER` | db + connection strings | Currently `recipe_admin` |
| `POSTGRES_PASSWORD` | db + connection strings | Falls back to a default if unset |
| `APP_API_KEY` | `verify_api_key()` (`app/core/security.py`) + Streamlit UI | Shared `X-API-Key` secret; defaults to `local_dev_secret_key_123` if unset. See `.env.example`. |
