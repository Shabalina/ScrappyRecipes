"""FastAPI endpoint contracts: parse returns a draft, confirm persists it.

Exercises the real routes through TestClient with `get_db` overridden and the
router / db-service stubbed, so neither Postgres nor an LLM is involved.

The central invariant is the two-step split:
    parse   -> 200, a draft, zero DB writes
    confirm -> 201, a saved row with an id

Note: TestClient is used *without* `with`, so the app's lifespan handler never
runs. That handler issues `CREATE EXTENSION vector` and `create_all` against a
real database, which is out of scope here.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.conftest import API_KEY_HEADERS

PARSE_TEXT = "/api/v1/recipes/parse-text"
PARSE_URL = "/api/v1/recipes/parse-url"
PARSE_IMAGES = "/api/v1/recipes/parse-images"
CONFIRM = "/api/v1/recipes/confirm"


def recipe_route(recipe_id):
    return f"/api/v1/recipes/{recipe_id}"


def saved_row_from(recipe, row_id=42):
    """A stand-in for the RecipeModel that save_parsed_recipe returns.

    Carries an `embedding` attribute on purpose: RecipeRead must drop it, and a
    row without one could not prove that.
    """
    return SimpleNamespace(
        id=row_id,
        title=recipe.title,
        description=recipe.description,
        prep_time_minutes=recipe.prep_time_minutes,
        cook_time_minutes=recipe.cook_time_minutes,
        servings=recipe.servings,
        ingredients=[i.model_dump() for i in recipe.ingredients],
        instructions=recipe.instructions,
        cooking_methods=recipe.cooking_methods,
        tags=recipe.tags,
        embedding=[0.25] * 1024,
    )


@pytest.fixture
def api(monkeypatch, sample_recipe, mock_db_session):
    """Returns a namespace of (client, route_and_parse mock, save mock, db double)."""
    import app.main as main

    route_and_parse = AsyncMock(return_value=sample_recipe)
    monkeypatch.setattr(main.router_service, "route_and_parse", route_and_parse)

    save = AsyncMock(side_effect=lambda recipe: saved_row_from(recipe))
    delete = AsyncMock(return_value=True)
    list_recipes = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(
        main,
        "RecipeDatabaseService",
        MagicMock(return_value=MagicMock(save_parsed_recipe=save, delete_recipe=delete, list_recipes=list_recipes)),
    )

    async def override_get_db():
        yield mock_db_session

    main.app.dependency_overrides[main.get_db] = override_get_db
    try:
        yield SimpleNamespace(
            client=TestClient(main.app, headers=API_KEY_HEADERS),
            route_and_parse=route_and_parse,
            save=save,
            delete=delete,
            list_recipes=list_recipes,
            db=mock_db_session,
        )
    finally:
        main.app.dependency_overrides.clear()


class TestParseReturnsDraft:
    def test_parse_text_returns_200_with_a_draft(self, api, sample_recipe):
        r = api.client.post(PARSE_TEXT, json={"text": "2 cups flour, fry them"})

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["title"] == sample_recipe.title
        assert len(body["ingredients"]) == 3

    def test_draft_carries_no_database_identity(self, api):
        body = api.client.post(PARSE_TEXT, json={"text": "anything"}).json()

        # A draft is not a row: no id, and no vector.
        assert "id" not in body
        assert "embedding" not in body

    def test_parse_never_writes_to_the_database(self, api):
        api.client.post(PARSE_TEXT, json={"text": "anything"})

        api.db.add.assert_not_called()
        api.db.commit.assert_not_awaited()

    def test_parse_url_forwards_the_url(self, api):
        r = api.client.post(PARSE_URL, json={"url": "https://example.com/recipe"})

        assert r.status_code == 200, r.text
        assert api.route_and_parse.await_args.kwargs["url"] == "https://example.com/recipe"

    def test_parse_images_forwards_bytes_and_mime_type(self, api):
        files = [
            ("files", ("p1.jpeg", b"page-one", "image/jpeg")),
            ("files", ("p2.jpeg", b"page-two", "image/jpeg")),
        ]

        r = api.client.post(PARSE_IMAGES, files=files)

        assert r.status_code == 200, r.text
        kwargs = api.route_and_parse.await_args.kwargs
        assert kwargs["image_bytes_list"] == [b"page-one", b"page-two"]
        assert kwargs["mime_type"] == "image/jpeg"

    def test_parse_images_preserves_png_mime_type(self, api):
        r = api.client.post(PARSE_IMAGES, files=[("files", ("p.png", b"x", "image/png"))])

        assert r.status_code == 200, r.text
        assert api.route_and_parse.await_args.kwargs["mime_type"] == "image/png"


class TestParseErrorMapping:
    def test_text_parse_failure_is_400(self, api):
        api.route_and_parse.side_effect = ValueError("Invalid input payload")

        r = api.client.post(PARSE_TEXT, json={"text": ""})

        assert r.status_code == 400
        assert "Invalid input payload" in r.json()["detail"]

    def test_unreachable_site_is_422(self, api):
        api.route_and_parse.side_effect = ValueError("Could not access the website")

        r = api.client.post(PARSE_URL, json={"url": "https://blocked.example"})

        assert r.status_code == 422
        assert "Could not access the website" in r.json()["detail"]

    def test_unexpected_url_failure_is_500(self, api):
        api.route_and_parse.side_effect = RuntimeError("upstream exploded")

        r = api.client.post(PARSE_URL, json={"url": "https://example.com"})

        assert r.status_code == 500
        assert "URL error" in r.json()["detail"]

    def test_unexpected_image_failure_is_500(self, api):
        api.route_and_parse.side_effect = RuntimeError("gemini down")

        r = api.client.post(PARSE_IMAGES, files=[("files", ("p.jpeg", b"x", "image/jpeg"))])

        assert r.status_code == 500
        assert "Image error" in r.json()["detail"]


class TestConfirmPersists:
    def test_confirm_returns_201_with_an_id(self, api, sample_recipe):
        r = api.client.post(CONFIRM, json=sample_recipe.model_dump())

        assert r.status_code == 201, r.text
        assert r.json()["id"] == 42

    def test_confirm_response_omits_the_embedding(self, api, sample_recipe):
        """The saved row has a 1024-float vector; the response must not carry it."""
        r = api.client.post(CONFIRM, json=sample_recipe.model_dump())

        assert "embedding" not in r.json()

    def test_confirm_saves_exactly_what_was_submitted(self, api, sample_recipe):
        api.client.post(CONFIRM, json=sample_recipe.model_dump())

        api.save.assert_awaited_once()
        submitted = api.save.await_args.args[0]
        assert submitted.title == sample_recipe.title
        assert len(submitted.ingredients) == 3

    def test_client_edits_are_what_gets_persisted(self, api, sample_recipe):
        """The whole point of the approval step: corrections must survive."""
        edited = sample_recipe.model_dump()
        edited["title"] = "Corrected Title"
        edited["servings"] = 8
        edited["ingredients"][0]["quantity"] = 3.0

        r = api.client.post(CONFIRM, json=edited)

        assert r.status_code == 201, r.text
        submitted = api.save.await_args.args[0]
        assert submitted.title == "Corrected Title"
        assert submitted.servings == 8
        assert submitted.ingredients[0].quantity == 3.0
        assert r.json()["title"] == "Corrected Title"

    @pytest.mark.parametrize(
        "mutate, reason",
        [
            (lambda d: d.pop("title"), "missing-title"),
            (lambda d: d.pop("ingredients"), "missing-ingredients"),
            (lambda d: d.pop("instructions"), "missing-instructions"),
            (lambda d: d.update(ingredients="not-a-list"), "ingredients-wrong-type"),
            (lambda d: d.update(servings="many"), "servings-not-an-int"),
        ],
    )
    def test_malformed_drafts_are_rejected_before_saving(self, api, sample_recipe, mutate, reason):
        payload = sample_recipe.model_dump()
        mutate(payload)

        r = api.client.post(CONFIRM, json=payload)

        assert r.status_code == 422, f"{reason} should be rejected"
        api.save.assert_not_awaited()

    def test_database_failure_is_500(self, api, sample_recipe):
        api.save.side_effect = RuntimeError("connection refused")

        r = api.client.post(CONFIRM, json=sample_recipe.model_dump())

        assert r.status_code == 500
        assert "Could not save recipe" in r.json()["detail"]


class TestDraftRoundTrip:
    def test_a_parse_response_is_a_valid_confirm_request(self, api):
        """The contract that ties the two endpoints together.

        If parse ever emits a shape confirm won't accept, the flow is broken for
        every client — this catches that directly.
        """
        draft = api.client.post(PARSE_TEXT, json={"text": "some recipe text"}).json()

        r = api.client.post(CONFIRM, json=draft)

        assert r.status_code == 201, r.text
        assert r.json()["id"] == 42
        assert r.json()["title"] == draft["title"]


class TestDeleteRecipe:
    def test_delete_returns_204_with_no_body(self, api):
        r = api.client.delete(recipe_route(42))

        assert r.status_code == 204
        assert r.content == b""
        api.delete.assert_awaited_once_with(42)

    def test_delete_missing_recipe_is_404(self, api):
        api.delete.return_value = False

        r = api.client.delete(recipe_route(999))

        assert r.status_code == 404
        assert "999" in r.json()["detail"]

    def test_delete_database_failure_is_500(self, api):
        api.delete.side_effect = RuntimeError("connection refused")

        r = api.client.delete(recipe_route(42))

        assert r.status_code == 500
        assert "Could not delete recipe" in r.json()["detail"]

    def test_non_integer_id_is_422(self, api):
        r = api.client.delete("/api/v1/recipes/not-an-int")

        assert r.status_code == 422
        api.delete.assert_not_awaited()


class TestListRecipes:
    ROUTE = "/api/v1/recipes"

    def test_returns_items_with_pagination_metadata(self, api, sample_recipe):
        rows = [saved_row_from(sample_recipe, row_id=i) for i in (3, 2, 1)]
        api.list_recipes.return_value = (rows, 3)

        r = api.client.get(self.ROUTE, params={"skip": 0, "limit": 20})

        assert r.status_code == 200, r.text
        body = r.json()
        assert [item["id"] for item in body["items"]] == [3, 2, 1]
        assert body["total"] == 3
        assert body["page"] == 1
        assert body["limit"] == 20

    def test_response_omits_the_embedding(self, api, sample_recipe):
        api.list_recipes.return_value = ([saved_row_from(sample_recipe, row_id=1)], 1)

        r = api.client.get(self.ROUTE)

        assert "embedding" not in r.json()["items"][0]

    def test_empty_library_returns_empty_items(self, api):
        api.list_recipes.return_value = ([], 0)

        r = api.client.get(self.ROUTE)

        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0, "page": 1, "limit": 20}

    def test_page_number_reflects_skip_and_limit(self, api, sample_recipe):
        api.list_recipes.return_value = ([saved_row_from(sample_recipe, row_id=1)], 45)

        r = api.client.get(self.ROUTE, params={"skip": 40, "limit": 20})

        assert r.status_code == 200, r.text
        assert r.json()["page"] == 3
        api.list_recipes.assert_awaited_once_with(skip=40, limit=20)

    def test_negative_skip_is_422(self, api):
        r = api.client.get(self.ROUTE, params={"skip": -1})

        assert r.status_code == 422

    def test_limit_above_max_is_422(self, api):
        r = api.client.get(self.ROUTE, params={"limit": 101})

        assert r.status_code == 422

    def test_database_failure_is_500(self, api):
        api.list_recipes.side_effect = RuntimeError("connection refused")

        r = api.client.get(self.ROUTE)

        assert r.status_code == 500
        assert "Could not list recipes" in r.json()["detail"]


class TestLocalSearch:
    ROUTE = "/api/v1/recipes/search"

    def _mock_search(self, monkeypatch, api, rows):
        """rows: list of (row, distance) tuples, as pgvector's ORDER BY <=> returns them."""
        import app.main as main

        monkeypatch.setattr(main, "generate_embedding", AsyncMock(return_value=[0.1] * 1024))
        api.db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=rows)))

    def test_returns_top_result_with_distance(self, api, monkeypatch, sample_recipe):
        row = saved_row_from(sample_recipe, row_id=7)
        self._mock_search(monkeypatch, api, [(row, 0.2913695694660686)])

        r = api.client.get(self.ROUTE, params={"q": "mushroom tart", "limit": 1})

        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["id"] == 7
        assert body[0]["distance"] == pytest.approx(0.2913695694660686)

    def test_response_omits_the_embedding(self, api, monkeypatch, sample_recipe):
        row = saved_row_from(sample_recipe, row_id=7)
        self._mock_search(monkeypatch, api, [(row, 0.3)])

        r = api.client.get(self.ROUTE, params={"q": "anything"})

        assert "embedding" not in r.json()[0]

    def test_no_rows_returns_empty_list(self, api, monkeypatch):
        self._mock_search(monkeypatch, api, [])

        r = api.client.get(self.ROUTE, params={"q": "nothing like this exists"})

        assert r.status_code == 200
        assert r.json() == []

    def test_blank_query_is_400(self, api):
        r = api.client.get(self.ROUTE, params={"q": "   "})

        assert r.status_code == 400

    def test_search_failure_is_500(self, api, monkeypatch):
        import app.main as main

        monkeypatch.setattr(main, "generate_embedding", AsyncMock(side_effect=RuntimeError("openai down")))

        r = api.client.get(self.ROUTE, params={"q": "lasagna"})

        assert r.status_code == 500
        assert "Search failed" in r.json()["detail"]


class TestSearchWeb:
    ROUTE = "/api/v1/recipes/search-web"

    def test_returns_top_results(self, api, monkeypatch):
        import app.main as main

        rows = [
            {"title": "Best Lasagna", "url": "https://example.com/lasagna", "snippet": "A classic."},
        ]
        search = MagicMock(return_value=rows)
        monkeypatch.setattr(main, "search_recipes_web", search)

        r = api.client.get(self.ROUTE, params={"query": "lasagna"})

        assert r.status_code == 200, r.text
        assert r.json() == rows
        search.assert_called_once_with("lasagna", max_results=3)

    def test_blank_query_is_400(self, api):
        r = api.client.get(self.ROUTE, params={"query": "   "})

        assert r.status_code == 400

    def test_search_failure_is_500(self, api, monkeypatch):
        import app.main as main

        monkeypatch.setattr(main, "search_recipes_web", MagicMock(side_effect=RuntimeError("ddgs down")))

        r = api.client.get(self.ROUTE, params={"query": "lasagna"})

        assert r.status_code == 500
        assert "Web search failed" in r.json()["detail"]


class TestUnchangedEndpoints:
    def test_health_still_ok(self, api):
        r = api.client.get("/health")

        assert r.status_code == 200
        assert r.json()["status"] == "ok"
