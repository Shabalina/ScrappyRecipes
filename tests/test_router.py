"""LLMRouterService — route selection, precedence, and optional DB persistence.

The router's job is dispatch, so these tests assert *which* downstream call it
makes rather than re-testing the parsers themselves.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas import RecipeCreate


@pytest.fixture
def router(monkeypatch, sample_recipe):
    """A router with its parser and scraper replaced by recording doubles."""
    import app.services.router_service as router_service

    monkeypatch.setattr(router_service, "RecipeParserService", MagicMock)
    monkeypatch.setattr(router_service, "RecipeScraperService", MagicMock)

    service = router_service.LLMRouterService()
    service.parser.parse_text_recipe = AsyncMock(return_value=sample_recipe)
    service.parser.parse_images_recipe = AsyncMock(return_value=sample_recipe)
    service.scraper.fetch_and_clean_html = AsyncMock(return_value="cleaned page text")
    return service


class TestRouteSelection:
    async def test_text_routes_to_text_parser(self, router, sample_recipe):
        result = await router.route_and_parse(raw_text="2 eggs, 1 cup milk. Mix and fry.")

        assert result is sample_recipe
        router.parser.parse_text_recipe.assert_awaited_once_with(
            raw_text="2 eggs, 1 cup milk. Mix and fry."
        )
        router.parser.parse_images_recipe.assert_not_awaited()

    async def test_images_route_to_image_parser(self, router, sample_recipe):
        pages = [b"page1", b"page2"]

        result = await router.route_and_parse(image_bytes_list=pages)

        assert result is sample_recipe
        router.parser.parse_images_recipe.assert_awaited_once_with(
            image_bytes_list=pages, mime_type="image/jpeg"
        )
        router.parser.parse_text_recipe.assert_not_awaited()

    async def test_url_scrapes_then_parses_the_cleaned_text(self, router):
        await router.route_and_parse(url="https://example.com/recipe")

        router.scraper.fetch_and_clean_html.assert_awaited_once_with(
            "https://example.com/recipe"
        )
        # The parser must receive the *scraped* text, not the URL itself.
        router.parser.parse_text_recipe.assert_awaited_once_with(
            raw_text="cleaned page text"
        )

    async def test_custom_mime_type_is_forwarded(self, router):
        await router.route_and_parse(image_bytes_list=[b"png"], mime_type="image/png")

        assert (
            router.parser.parse_images_recipe.await_args.kwargs["mime_type"]
            == "image/png"
        )


class TestRoutePrecedence:
    async def test_url_wins_over_images_and_text(self, router):
        await router.route_and_parse(
            url="https://example.com/r", image_bytes_list=[b"x"], raw_text="text"
        )

        router.scraper.fetch_and_clean_html.assert_awaited_once()
        router.parser.parse_images_recipe.assert_not_awaited()
        router.parser.parse_text_recipe.assert_awaited_once_with(
            raw_text="cleaned page text"
        )

    async def test_images_win_over_text(self, router):
        await router.route_and_parse(image_bytes_list=[b"x"], raw_text="some text")

        router.parser.parse_images_recipe.assert_awaited_once()
        router.parser.parse_text_recipe.assert_not_awaited()


class TestInvalidInput:
    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({}, id="nothing"),
            pytest.param({"raw_text": ""}, id="empty-text"),
            pytest.param({"raw_text": "   "}, id="whitespace-text"),
            pytest.param({"url": "  "}, id="whitespace-url"),
            pytest.param({"image_bytes_list": []}, id="empty-image-list"),
        ],
    )
    async def test_rejects_empty_payloads(self, router, kwargs):
        with pytest.raises(ValueError, match="Invalid input payload"):
            await router.route_and_parse(**kwargs)


class TestNoPersistence:
    """The router parses only. Saving is /api/v1/recipes/confirm's job."""

    async def test_returns_an_unsaved_draft(self, router, sample_recipe):
        result = await router.route_and_parse(raw_text="text")

        assert isinstance(result, RecipeCreate)
        assert result is sample_recipe
        # A draft has no database identity yet.
        assert not hasattr(result, "id")

    async def test_no_longer_accepts_a_db_session(self, router, mock_db_session):
        """Guards the split: a stale `db=` caller should fail loudly, not silently save."""
        with pytest.raises(TypeError, match="db"):
            await router.route_and_parse(raw_text="text", db=mock_db_session)

    async def test_router_module_does_not_import_the_db_service(self):
        """Structural check: parsing must not be able to reach persistence."""
        import app.services.router_service as router_service

        assert not hasattr(router_service, "RecipeDatabaseService")

    async def test_never_generates_an_embedding(self, router, monkeypatch):
        """Embedding spend belongs at confirm time, not on discarded drafts."""
        import app.services.embedding_service as embedding_service

        called = False

        async def spy(*_a, **_k):
            nonlocal called
            called = True
            return [0.0] * 1024

        monkeypatch.setattr(embedding_service, "generate_embedding", spy)

        await router.route_and_parse(raw_text="text")

        assert called is False
