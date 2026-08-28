# tests/test_shopping_service.py
"""Tests for app/services/shopping_service.py and its endpoint in
app/routers/menu.py.

Service-level tests exercise `generate_menu_shopping_list` directly against
`mock_db_session`, with a fake `parser` injected so no OpenAI call happens.
Endpoint-level tests hit `GET /api/v1/menus/{menu_id}/shopping-list` through
TestClient with `get_db` overridden and `generate_menu_shopping_list` stubbed,
mirroring the style of tests/test_menu_router.py.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.schemas import ShoppingListCategory, ShoppingListItem, ShoppingListResult
from app.services import shopping_service

SHOPPING_LIST_URL = "/api/v1/menus/{menu_id}/shopping-list"

SAMPLE_SHOPPING_LIST = ShoppingListResult(
    categories=[
        ShoppingListCategory(
            category="Produce",
            items=[
                ShoppingListItem(
                    item="Brown Onion",
                    quantity="3",
                    unit="medium",
                    sources=["Beef Stew", "Tomato Soup"],
                ),
            ],
        ),
    ]
)


def make_menu(id, recipe_ids, shopping_list=None):
    return SimpleNamespace(id=id, recipe_ids=recipe_ids, shopping_list=shopping_list)


def make_recipe(id, title, ingredients=None):
    return SimpleNamespace(id=id, title=title, ingredients=ingredients or [])


def set_recipe_rows(mock_db_session, recipes):
    mock_db_session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=recipes))))
    )


# --------------------------------------------------------------------------
# Service-level tests
# --------------------------------------------------------------------------

class TestGenerateMenuShoppingList:
    async def test_returns_none_when_menu_not_found(self, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)

        result = await shopping_service.generate_menu_shopping_list(mock_db_session, menu_id=99)

        assert result is None

    async def test_returns_cached_list_without_calling_the_llm(self, mock_db_session):
        cached = {"categories": [{"category": "Produce", "items": []}]}
        mock_db_session.get = AsyncMock(return_value=make_menu(1, recipe_ids=[10], shopping_list=cached))
        fake_parser = MagicMock()
        fake_parser.generate_shopping_list = AsyncMock()

        result = await shopping_service.generate_menu_shopping_list(mock_db_session, menu_id=1, parser=fake_parser)

        assert result == cached
        fake_parser.generate_shopping_list.assert_not_called()
        mock_db_session.commit.assert_not_awaited()

    async def test_generates_and_caches_when_absent(self, mock_db_session):
        menu = make_menu(1, recipe_ids=[10, 20], shopping_list=None)
        mock_db_session.get = AsyncMock(return_value=menu)
        set_recipe_rows(
            mock_db_session,
            [make_recipe(10, "Beef Stew"), make_recipe(20, "Tomato Soup")],
        )
        fake_parser = MagicMock()
        fake_parser.generate_shopping_list = AsyncMock(return_value=SAMPLE_SHOPPING_LIST)

        result = await shopping_service.generate_menu_shopping_list(mock_db_session, menu_id=1, parser=fake_parser)

        assert result == SAMPLE_SHOPPING_LIST.model_dump()
        assert menu.shopping_list == SAMPLE_SHOPPING_LIST.model_dump()
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(menu)

    async def test_recipes_are_passed_in_menu_order_and_missing_ones_dropped(self, mock_db_session):
        # recipe 20 was deleted after the menu was confirmed.
        menu = make_menu(1, recipe_ids=[20, 10], shopping_list=None)
        mock_db_session.get = AsyncMock(return_value=menu)
        recipe_10 = make_recipe(10, "Beef Stew")
        set_recipe_rows(mock_db_session, [recipe_10])  # DB only returns the surviving recipe
        fake_parser = MagicMock()
        fake_parser.generate_shopping_list = AsyncMock(return_value=SAMPLE_SHOPPING_LIST)

        await shopping_service.generate_menu_shopping_list(mock_db_session, menu_id=1, parser=fake_parser)

        passed_recipes = fake_parser.generate_shopping_list.await_args.args[0]
        assert passed_recipes == [recipe_10]

    async def test_creates_a_default_parser_when_none_is_injected(self, monkeypatch, mock_db_session):
        menu = make_menu(1, recipe_ids=[10], shopping_list=None)
        mock_db_session.get = AsyncMock(return_value=menu)
        set_recipe_rows(mock_db_session, [make_recipe(10, "Beef Stew")])

        fake_parser_instance = MagicMock()
        fake_parser_instance.generate_shopping_list = AsyncMock(return_value=SAMPLE_SHOPPING_LIST)
        fake_parser_cls = MagicMock(return_value=fake_parser_instance)
        monkeypatch.setattr(shopping_service, "RecipeParserService", fake_parser_cls)

        result = await shopping_service.generate_menu_shopping_list(mock_db_session, menu_id=1)

        fake_parser_cls.assert_called_once()
        assert result == SAMPLE_SHOPPING_LIST.model_dump()


# --------------------------------------------------------------------------
# Endpoint-level tests
# --------------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch, mock_db_session):
    import app.main as main

    generate_menu_shopping_list = AsyncMock(return_value=SAMPLE_SHOPPING_LIST.model_dump())
    monkeypatch.setattr("app.routers.menu.generate_menu_shopping_list", generate_menu_shopping_list)

    async def override_get_db():
        yield mock_db_session

    main.app.dependency_overrides[main.get_db] = override_get_db
    try:
        yield SimpleNamespace(
            client=TestClient(main.app),
            generate_menu_shopping_list=generate_menu_shopping_list,
            db=mock_db_session,
        )
    finally:
        main.app.dependency_overrides.clear()


class TestShoppingListEndpoint:
    def test_returns_shopping_list(self, api):
        r = api.client.get(SHOPPING_LIST_URL.format(menu_id=1))

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["categories"][0]["category"] == "Produce"
        assert body["categories"][0]["items"][0]["item"] == "Brown Onion"
        assert body["categories"][0]["items"][0]["sources"] == ["Beef Stew", "Tomato Soup"]

    def test_menu_not_found_is_404(self, api):
        api.generate_menu_shopping_list.return_value = None

        r = api.client.get(SHOPPING_LIST_URL.format(menu_id=999))

        assert r.status_code == 404
        assert "999" in r.json()["detail"]

    def test_service_failure_is_500(self, api):
        api.generate_menu_shopping_list.side_effect = RuntimeError("openai down")

        r = api.client.get(SHOPPING_LIST_URL.format(menu_id=1))

        assert r.status_code == 500
        assert "Could not generate shopping list" in r.json()["detail"]

    def test_menu_id_is_forwarded(self, api):
        api.client.get(SHOPPING_LIST_URL.format(menu_id=42))

        assert api.generate_menu_shopping_list.await_args.args[1] == 42
