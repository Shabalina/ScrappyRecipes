# CLAUDE.md - Scrappy Recipes Context & Roadmap

## 1. Project Overview & Architecture
Scrappy Recipes is an AI-powered recipe extraction and semantic search service built with FastAPI, PostgreSQL + pgvector, and LLMs (Amazon Bedrock for text parsing, shopping lists, and embeddings by default; Gemini for image parsing; OpenAI available only as an explicit embeddings opt-out).

* **Backend Framework:** FastAPI (Async)
* **Database & Vector Store:** PostgreSQL with `pgvector` extension (Dockerized)
* **ORM & Migrations:** Async SQLAlchemy 2.0 + Alembic
* **LLMs & Embeddings:**
  * **Amazon Bedrock, unconditional for text parsing & shopping lists** (since 2026-09-01) —
    Claude 3.5 Haiku via `RecipeParserService.parse_text_recipe()` /
    `.generate_shopping_list()` — `app/services/bedrock_service.py`, `app/services/llm_parser.py`.
    There is no OpenAI fallback for these two routes anymore; `AI_PROVIDER` has no effect on them.
  * **Amazon Bedrock, default for embeddings** (`AI_PROVIDER=bedrock`, the default in
    `app/core/config.py`) — Titan Embed Text v2 — `app/services/bedrock_service.py`.
  * OpenAI `text-embedding-3-small` (requested at 1024 dims via `dimensions=1024`) for vector
    search embeddings, available only as an explicit opt-out when `AI_PROVIDER` is set away
    from `"bedrock"` (e.g. `"gemini"`/`"openai"`) — `app/services/embedding_service.py`. This is
    the *only* place OpenAI is still reachable in production code.
  * Gemini `gemini-3.5-flash` for vision/multimodal image parsing — `app/services/llm_parser.py`
    (verified working 2026-08-09). **Always Gemini regardless of `AI_PROVIDER`** — Claude 3.5
    Haiku is text-only, so there is no Bedrock vision route.
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
| `gemini_client.models.generate_content` | `mock_gemini_generate` (returns JSON *string*) |
| `boto3.client("bedrock-runtime").invoke_model` | `mock_boto_client` in `tests/test_bedrock_service.py` |
| `httpx.AsyncClient` | `httpx.MockTransport` in `tests/test_scraper.py` |
| `AsyncOpenAI` (embeddings opt-out only) | patched in `tests/test_persistence.py` |
| `AsyncSession` | `mock_db_session` (`add` sync; `commit`/`refresh`/`get`/`delete`/`execute`/`scalar` async) |

An autouse `_no_live_api` fixture overwrites both LLM API keys with dummies, pins `APP_API_KEY`
to `TEST_API_KEY`, and replaces `boto3.client` with a function that raises loudly if called
unmocked (`tests/conftest.py`) — since `AI_PROVIDER` defaults to `"bedrock"`, this is what turns
an under-mocked test into an immediate, loud failure instead of a live call to AWS Bedrock.
Together these mean a missing mock fails loudly on a stub instead of
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
│   │   ├── config.py                # Settings — AI_PROVIDER + Bedrock env vars, lazily read
│   │   └── security.py             # verify_api_key() — X-API-Key header check against APP_API_KEY
│   ├── database.py                 # Async DB engine & session dependency
│   ├── main.py                     # FastAPI entry point, lifespan, routes
│   ├── models.py                   # SQLAlchemy RecipeModel (includes Vector column), MenuModel
│   ├── schemas.py                  # Pydantic schemas (RecipeRead, ParseTextRequest, etc.)
│   └── services/
│       ├── bedrock_service.py      # BedrockService — Claude 3.5 Haiku (parsing/shopping list) +
│                                    # Titan Embed Text v2 (embeddings) via boto3 bedrock-runtime
│       ├── embedding_service.py    # generate_embedding() — OpenAI text-embedding-3-small, or
│                                    # Bedrock Titan when AI_PROVIDER=bedrock
│       ├── llm_parser.py           # RecipeParserService: text parsing + generate_shopping_list()
│                                    # (always Bedrock Claude, lazy client) + image parsing
│                                    # (always Gemini, lazy client)
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
│   ├── test_bedrock_service.py     # BedrockService (Claude parsing/shopping list + Titan
│                                    # embeddings) and AI_PROVIDER dispatch, boto3 stubbed
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
├── manage_db.py                    # DB initialization / --migrate / --reembed script
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
- [x] Amazon Bedrock is now unconditional for text parsing + shopping list consolidation (Claude
  3.5 Haiku) and the **default** for embeddings (Titan Embed Text v2, `AI_PROVIDER=bedrock`,
  since 2026-09-01). OpenAI remains available only as an explicit embeddings opt-out; Gemini
  always handles image parsing (see below).

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

`RecipeRead` does not expose the `embedding` column: it is 1024 floats (~17KB of JSON) per row,
no client consumes it, and it multiplied `/search` payloads considerably. `RecipeSearchResult` (used
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
`penalty: float`, `final_score: float`, `match_score: float`). Ranking/truncation still uses
`final_score` (ascending, lower wins) — `match_score = 1 - final_score` is a purely presentational
field, added so UI/API consumers can show "higher is a better match" without inverting the sort
key themselves. `GET /api/v1/menu/slot-candidates` (below) wraps each one in `SlotCandidateRead`
(`recipe: RecipeRead`) for the API boundary, including `match_score`. Covered by
`tests/test_menu_service.py` (exclusion via inspecting the compiled `NOT IN` clause params, penalty
demotion changing rank order, expired/never-used penalties being exactly `0.0`, and
`match_score == 1 - final_score`). The
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
   always Claude 3.5 Haiku on Bedrock, mirroring `parse_text_recipe`) is given
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
  (up to 3) results renders title, cook time, and `match_score` (`1 - final_score`, so higher
  reads as a better match), with a **+ Add to Menu** button
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

### Amazon Bedrock provider — `app/services/bedrock_service.py`
Uses `boto3.client("bedrock-runtime", region_name=...)` directly (`invoke_model`), not a
higher-level SDK, so text parsing/shopping-list and Titan embeddings share one client shape.
`RecipeParserService` (`app/services/llm_parser.py`) constructs its `BedrockService` **lazily**
via a `bedrock_service` property (constructed on first use, not in `__init__`) — same pattern as
its `gemini_client` property — so a Bedrock-only deployment with no `GEMINI_API_KEY`/
`OPENAI_API_KEY` at all doesn't crash at import/startup time; `boto3.client()` itself never
validates AWS credentials eagerly either. Every embedding/parsing/shopping-list call in the
codebase goes through the centralized `generate_embedding()` (`app/services/embedding_service.py`)
and `RecipeParserService` (`app/services/llm_parser.py`) — the menu slot-candidate query embedding
(`app/services/menu_service.py`), the `/search` query embedding (`app/main.py`), and the
recipe-confirm embedding (`app/services/recipe_db_service.py`) all call `generate_embedding()`
rather than any provider SDK directly.

* **Text parsing & shopping list consolidation are Bedrock-only, unconditionally** —
  `RecipeParserService.parse_text_recipe()` and `.generate_shopping_list()`
  (`app/services/llm_parser.py`) call `self.bedrock_service` directly with no provider check;
  `AI_PROVIDER` has no effect on these two routes. The OpenAI `gpt-4o-mini` path that used to serve
  as their fallback was removed 2026-09-01 (`self.openai_client` and the `openai` import are gone
  from this file entirely) — that history lives in `tests/test_bedrock_service.py` now, not
  `tests/test_parsers.py`, which covers Gemini image parsing only.
  `BedrockService._invoke_claude_tool()` calls `BEDROCK_LLM_MODEL_ID` (default
  `anthropic.claude-3-5-haiku-20241022-v1:0`) via `invoke_model` with a single tool forced via
  `tool_choice: {"type": "tool", "name": ...}` — the Bedrock `invoke_model` equivalent of OpenAI's
  `beta.chat.completions.parse` / Gemini's `response_schema`, since Bedrock's `invoke_model` path
  has no native structured-output mode. The tool's `input_schema` is generated directly from
  `RecipeCreate.model_json_schema()` / `ShoppingListResult.model_json_schema()`. **Image parsing
  stays on Gemini regardless of `AI_PROVIDER`** — Claude 3.5 Haiku is text-only, so there is no
  Bedrock vision route.
* **Embeddings still have a provider switch** — `generate_embedding()`
  (`app/services/embedding_service.py`) checks `settings.AI_PROVIDER` (`app/core/config.py`,
  lazily read from `os.environ`, defaults to `"bedrock"`) and delegates to
  `BedrockService.generate_embedding()` (`BEDROCK_EMBEDDING_MODEL_ID`, default
  `amazon.titan-embed-text-v2:0`, via `invoke_model`) unless it's explicitly set away from
  `"bedrock"` (e.g. `"gemini"`/`"openai"`), in which case it falls through to OpenAI's
  `text-embedding-3-small`. This is now the **only** place `AI_PROVIDER` still branches, and the
  only place OpenAI is still reachable from production code — kept because
  `RecipeModel.embedding` (`app/models.py`, a `Vector(1024)` column) is a shared, provider-neutral
  vector store: Titan Embed Text v2 outputs 1024 dims natively (its cap), and the OpenAI opt-out
  path requests the same size explicitly via `dimensions=1024` (native Matryoshka truncation, not
  padding), so both write directly comparable vectors into the same column.
* **Docker Compose** (`docker-compose.yml`) sets `AI_PROVIDER=${AI_PROVIDER:-bedrock}`,
  `AWS_REGION=${AWS_REGION:-eu-west-1}`, `AWS_PROFILE=${AWS_PROFILE:-default}`, and mounts
  `~/.aws:/root/.aws:ro` into the `app` container so local developers get working Bedrock calls
  out of the box, reusing whatever AWS credentials/SSO profile are already configured on the host
  — no AWS secrets need to be duplicated into `.env`. The mount is read-only, but it does expose
  the host's full `~/.aws` (all profiles, not just the one in use) inside the container.
  `OPENAI_API_KEY` is still passed through (`docker-compose.yml`, `.env.example`) and `openai`
  is still in `requirements.txt` — both are kept deliberately, since the embeddings opt-out above
  still needs them; they are not dead weight.
* **Test-suite safety net** — `tests/conftest.py`'s autouse `_no_live_api` fixture patches
  `bedrock_service.boto3.client` to a function that raises `RuntimeError` by default, the same
  "fail loudly on a missing mock" guarantee it already gives OpenAI/Gemini keys. This matters
  specifically because `AI_PROVIDER` defaults to `"bedrock"`: without this guard, any test
  exercising the real `generate_embedding()`/`parse_text_recipe()`/`generate_shopping_list()`
  without its own mock would place a live call to AWS Bedrock on a host with working credentials,
  instead of failing. `tests/test_persistence.py::TestGenerateEmbedding` (the one remaining
  OpenAI-specific test, for the embeddings opt-out) pins `AI_PROVIDER=gemini` via
  `monkeypatch.setenv` for that reason.
* Covered by `tests/test_bedrock_service.py` with `boto3.client("bedrock-runtime")` stubbed:
  Titan's native 1024-dim output, the `dimensions` request shape, the forced-tool-choice request
  shape for both Claude routes, and provider-dispatch tests confirming text parsing always routes
  to Bedrock and that the embeddings opt-out (`AI_PROVIDER=gemini`) still works end-to-end.

### Re-embedding management script — `manage_db.py --reembed`
`run_reembed()` (`manage_db.py`) fetches every `RecipeModel` row, rebuilds each one's embedding
text via the existing `build_recipe_embedding_text()` (`app/services/embedding_service.py`, so the
text fed to the model matches what `/confirm` would have produced), regenerates its embedding via
`BedrockService.generate_embedding()` — unconditionally, regardless of `AI_PROVIDER` — and commits
all updates in a single transaction. It connects directly via `create_async_engine(APP_DB_URL)`
rather than the FastAPI `get_db` dependency, since it runs standalone via
`python manage_db.py --reembed` (run from the host against the exposed `localhost:5432`, or inside
the `app` container after a rebuild). Intended for one-off backfills after an embedding-dimension
or provider change, not routine use — it makes one real Bedrock call per recipe. `--reembed` can be
combined with `--migrate` in one invocation; migrations run first.

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
| `AI_PROVIDER` | `Settings.AI_PROVIDER` (`app/core/config.py`) | `"bedrock"` (default) or `"gemini"`/`"openai"` to opt embeddings back onto OpenAI. Only affects embeddings — text parsing/shopping-list are always Bedrock and image parsing is always Gemini, regardless of this setting. |
| `AWS_REGION` | `BedrockService` (`app/services/bedrock_service.py`) | Region for the `bedrock-runtime` client. Defaults to `eu-west-1`. Also needs standard AWS credentials available to `boto3` (env vars, shared config, or an instance/task role) — not listed here since `boto3` resolves them itself. In Docker Compose, `~/.aws:/root/.aws:ro` is mounted into the `app` container so the host's existing credentials/SSO profiles work without duplicating secrets into `.env`. |
| `AWS_PROFILE` | `boto3` (via the mounted `~/.aws`) | Named profile to use from the mounted AWS config/credentials files. Defaults to `default`. Only relevant in Docker Compose — set it if your host uses a non-default named profile for Bedrock access. |
| `BEDROCK_LLM_MODEL_ID` | `BedrockService` | Defaults to `anthropic.claude-3-5-haiku-20241022-v1:0`. |
| `BEDROCK_EMBEDDING_MODEL_ID` | `BedrockService` | Defaults to `amazon.titan-embed-text-v2:0`. See the dimension caveat above. |
