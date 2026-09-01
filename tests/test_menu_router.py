"""Tests for app/routers/menu.py — slot-candidates lookup and menu confirm.

Exercises the real routes through TestClient with `get_db` overridden and
`get_slot_candidates` stubbed, so neither Postgres nor OpenAI embeddings are
involved. Mirrors the style of tests/test_api.py.

Note: TestClient is used *without* `with`, so the app's lifespan handler
(which issues `CREATE EXTENSION vector` against a real database) never runs.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.services.menu_service import SlotCandidate
from tests.conftest import API_KEY_HEADERS

SLOT_CANDIDATES = "/api/v1/menu/slot-candidates"
CONFIRM = "/api/v1/menu/confirm"
MENUS = "/api/v1/menus"


def recipe_row(sample_recipe, recipe_id):
    """A stand-in for the RecipeModel a slot candidate wraps."""
    return SimpleNamespace(
        id=recipe_id,
        title=sample_recipe.title,
        description=sample_recipe.description,
        prep_time_minutes=sample_recipe.prep_time_minutes,
        cook_time_minutes=sample_recipe.cook_time_minutes,
        servings=sample_recipe.servings,
        ingredients=[i.model_dump() for i in sample_recipe.ingredients],
        instructions=sample_recipe.instructions,
        cooking_methods=sample_recipe.cooking_methods,
        tags=sample_recipe.tags,
    )


def menu_row(id, menu_number, recipe_ids, shopping_list=None, created_at=None):
    """A stand-in for the MenuModel a menu history entry wraps."""
    return SimpleNamespace(
        id=id,
        menu_number=menu_number,
        created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        recipe_ids=recipe_ids,
        shopping_list=shopping_list,
    )


def stub_list_menus_db(mock_db_session, menus, recipes=None):
    """Wires db.execute for GET /api/v1/menus: menus query, then (if any recipe
    ids are referenced) a second query for their metadata."""
    menus_result = MagicMock()
    menus_result.scalars.return_value.all.return_value = menus

    results = [menus_result]
    if recipes is not None:
        recipes_result = MagicMock()
        recipes_result.scalars.return_value.all.return_value = recipes
        results.append(recipes_result)

    mock_db_session.execute = AsyncMock(side_effect=results)


def stub_confirm_db(mock_db_session, max_menu_number, assigned_id=1):
    """Wires db.scalar (max menu_number lookup) and db.refresh (post-insert id/created_at)."""
    mock_db_session.scalar = AsyncMock(return_value=max_menu_number)

    async def fake_refresh(menu):
        menu.id = assigned_id
        menu.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    mock_db_session.refresh = AsyncMock(side_effect=fake_refresh)


@pytest.fixture
def api(monkeypatch, mock_db_session):
    """Returns a namespace of (client, get_slot_candidates mock, db double)."""
    import app.main as main

    get_slot_candidates = AsyncMock(return_value=[])
    monkeypatch.setattr("app.routers.menu.get_slot_candidates", get_slot_candidates)

    async def override_get_db():
        yield mock_db_session

    main.app.dependency_overrides[main.get_db] = override_get_db
    try:
        yield SimpleNamespace(
            client=TestClient(main.app, headers=API_KEY_HEADERS),
            get_slot_candidates=get_slot_candidates,
            db=mock_db_session,
        )
    finally:
        main.app.dependency_overrides.clear()


class TestSlotCandidates:
    def test_returns_candidates_with_scores(self, api, sample_recipe):
        candidate = SlotCandidate(
            recipe=recipe_row(sample_recipe, recipe_id=7),
            distance=0.2,
            penalty=0.05,
            final_score=0.25,
            match_score=0.75,
        )
        api.get_slot_candidates.return_value = [candidate]

        r = api.client.get(SLOT_CANDIDATES, params={"q": "quick weeknight soup"})

        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["recipe"]["id"] == 7
        assert body[0]["recipe"]["title"] == sample_recipe.title
        assert body[0]["distance"] == pytest.approx(0.2)
        assert body[0]["penalty"] == pytest.approx(0.05)
        assert body[0]["final_score"] == pytest.approx(0.25)
        assert body[0]["match_score"] == pytest.approx(0.75)

    def test_no_candidates_returns_empty_list(self, api):
        r = api.client.get(SLOT_CANDIDATES, params={"q": "soup"})

        assert r.status_code == 200
        assert r.json() == []

    def test_blank_query_is_400(self, api):
        r = api.client.get(SLOT_CANDIDATES, params={"q": "   "})

        assert r.status_code == 400

    def test_exclude_ids_are_parsed_and_forwarded(self, api):
        r = api.client.get(SLOT_CANDIDATES, params={"q": "soup", "exclude_ids": "1,2,3"})

        assert r.status_code == 200, r.text
        assert api.get_slot_candidates.await_args.kwargs["exclude_ids"] == [1, 2, 3]

    def test_no_exclude_ids_defaults_to_empty_list(self, api):
        api.client.get(SLOT_CANDIDATES, params={"q": "soup"})

        assert api.get_slot_candidates.await_args.kwargs["exclude_ids"] == []

    def test_invalid_exclude_ids_format_is_400(self, api):
        r = api.client.get(SLOT_CANDIDATES, params={"q": "soup", "exclude_ids": "1,abc,3"})

        assert r.status_code == 400
        api.get_slot_candidates.assert_not_awaited()

    def test_limit_is_forwarded(self, api):
        api.client.get(SLOT_CANDIDATES, params={"q": "soup", "limit": 2})

        assert api.get_slot_candidates.await_args.kwargs["limit"] == 2

    def test_limit_defaults_to_three(self, api):
        api.client.get(SLOT_CANDIDATES, params={"q": "soup"})

        assert api.get_slot_candidates.await_args.kwargs["limit"] == 3

    def test_limit_above_max_is_422(self, api):
        r = api.client.get(SLOT_CANDIDATES, params={"q": "soup", "limit": 7})

        assert r.status_code == 422

    def test_limit_below_min_is_422(self, api):
        r = api.client.get(SLOT_CANDIDATES, params={"q": "soup", "limit": 0})

        assert r.status_code == 422

    def test_service_failure_is_500(self, api):
        api.get_slot_candidates.side_effect = RuntimeError("db down")

        r = api.client.get(SLOT_CANDIDATES, params={"q": "soup"})

        assert r.status_code == 500
        assert "Could not get slot candidates" in r.json()["detail"]


class TestConfirmMenu:
    def test_confirm_creates_menu_and_returns_details(self, api):
        stub_confirm_db(api.db, max_menu_number=3, assigned_id=10)

        r = api.client.post(CONFIRM, json={"recipe_ids": [1, 2, 3]})

        assert r.status_code == 201, r.text
        body = r.json()
        assert body["id"] == 10
        assert body["menu_number"] == 4
        assert body["recipe_ids"] == [1, 2, 3]

    def test_confirm_when_no_menus_yet_starts_at_one(self, api):
        stub_confirm_db(api.db, max_menu_number=None)

        r = api.client.post(CONFIRM, json={"recipe_ids": [1]})

        assert r.status_code == 201, r.text
        assert r.json()["menu_number"] == 1

    def test_confirm_updates_last_menu_number_for_the_given_recipe_ids(self, api):
        stub_confirm_db(api.db, max_menu_number=0)

        api.client.post(CONFIRM, json={"recipe_ids": [5, 6]})

        stmt = api.db.execute.call_args.args[0]
        compiled_params = stmt.compile().params
        assert [5, 6] in compiled_params.values()

    def test_confirm_commits_and_adds_the_menu_row(self, api):
        stub_confirm_db(api.db, max_menu_number=0)

        api.client.post(CONFIRM, json={"recipe_ids": [1]})

        api.db.add.assert_called_once()
        api.db.commit.assert_awaited_once()

    def test_recipe_ids_empty_list_is_422(self, api):
        r = api.client.post(CONFIRM, json={"recipe_ids": []})

        assert r.status_code == 422
        api.db.commit.assert_not_awaited()

    def test_recipe_ids_more_than_six_is_422(self, api):
        r = api.client.post(CONFIRM, json={"recipe_ids": [1, 2, 3, 4, 5, 6, 7]})

        assert r.status_code == 422
        api.db.commit.assert_not_awaited()

    def test_database_failure_is_500(self, api):
        api.db.scalar = AsyncMock(side_effect=RuntimeError("connection refused"))

        r = api.client.post(CONFIRM, json={"recipe_ids": [1]})

        assert r.status_code == 500
        assert "Could not confirm menu" in r.json()["detail"]


class TestListMenus:
    def test_returns_menus_with_recipe_metadata(self, api, sample_recipe):
        menu = menu_row(id=10, menu_number=4, recipe_ids=[1, 2])
        recipes = [recipe_row(sample_recipe, 1), recipe_row(sample_recipe, 2)]
        stub_list_menus_db(api.db, [menu], recipes)

        r = api.client.get(MENUS)

        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["id"] == 10
        assert body[0]["menu_number"] == 4
        assert [rec["id"] for rec in body[0]["recipes"]] == [1, 2]
        assert body[0]["recipes"][0]["title"] == sample_recipe.title
        assert body[0]["recipes"][0]["cook_time_minutes"] == sample_recipe.cook_time_minutes

    def test_no_menus_returns_empty_list(self, api):
        stub_list_menus_db(api.db, [])

        r = api.client.get(MENUS)

        assert r.status_code == 200
        assert r.json() == []
        # Only the menus query should run — no recipe ids to look up.
        assert api.db.execute.await_count == 1

    def test_missing_recipe_is_omitted_not_errored(self, api, sample_recipe):
        menu = menu_row(id=1, menu_number=1, recipe_ids=[1, 99])
        recipes = [recipe_row(sample_recipe, 1)]  # 99 was deleted after this menu was confirmed
        stub_list_menus_db(api.db, [menu], recipes)

        r = api.client.get(MENUS)

        assert r.status_code == 200, r.text
        assert [rec["id"] for rec in r.json()[0]["recipes"]] == [1]

    def test_orders_by_menu_number_descending(self, api):
        stub_list_menus_db(api.db, [])

        api.client.get(MENUS)

        stmt = api.db.execute.call_args_list[0].args[0]
        assert "ORDER BY menus.menu_number DESC" in str(stmt)

    def test_limit_and_skip_are_forwarded(self, api):
        stub_list_menus_db(api.db, [])

        r = api.client.get(MENUS, params={"limit": 5, "skip": 10})

        assert r.status_code == 200, r.text
        stmt = api.db.execute.call_args_list[0].args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 5" in compiled
        assert "OFFSET 10" in compiled

    def test_limit_defaults_to_ten(self, api):
        stub_list_menus_db(api.db, [])

        api.client.get(MENUS)

        stmt = api.db.execute.call_args_list[0].args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 10" in compiled

    def test_limit_above_max_is_422(self, api):
        r = api.client.get(MENUS, params={"limit": 101})

        assert r.status_code == 422

    def test_skip_below_zero_is_422(self, api):
        r = api.client.get(MENUS, params={"skip": -1})

        assert r.status_code == 422

    def test_database_failure_is_500(self, api):
        api.db.execute = AsyncMock(side_effect=RuntimeError("connection refused"))

        r = api.client.get(MENUS)

        assert r.status_code == 500
        assert "Could not list menus" in r.json()["detail"]
