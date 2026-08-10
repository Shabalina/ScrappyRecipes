"""search_recipes_web — mocks `DDGS.text` so no real network call is made."""

from unittest.mock import MagicMock

import pytest

from app.schemas import WebSearchResult
from app.services.web_search_service import search_recipes_web

DDGS_ROWS = [
    {"title": "Best Lasagna", "href": "https://example.com/lasagna", "body": "A classic lasagna recipe."},
    {"title": "Vegan Lasagna", "href": "https://example.com/vegan-lasagna", "body": "No dairy, no eggs."},
]


@pytest.fixture
def mock_ddgs(monkeypatch):
    import app.services.web_search_service as web_search_service

    text = MagicMock(return_value=DDGS_ROWS)
    monkeypatch.setattr(web_search_service, "DDGS", MagicMock(return_value=MagicMock(text=text)))
    return text


def test_returns_web_search_results(mock_ddgs):
    results = search_recipes_web("lasagna")

    assert all(isinstance(r, WebSearchResult) for r in results)
    assert results[0].title == "Best Lasagna"
    assert results[0].url == "https://example.com/lasagna"
    assert results[0].snippet == "A classic lasagna recipe."


def test_forwards_query_and_max_results(mock_ddgs):
    search_recipes_web("lasagna", max_results=3)

    mock_ddgs.assert_called_once_with("lasagna recipe cooking", max_results=3)


def test_missing_fields_default_to_empty_strings(monkeypatch):
    import app.services.web_search_service as web_search_service

    monkeypatch.setattr(
        web_search_service, "DDGS", MagicMock(return_value=MagicMock(text=MagicMock(return_value=[{}])))
    )

    results = search_recipes_web("lasagna")

    assert results == [WebSearchResult(title="", url="", snippet="")]
