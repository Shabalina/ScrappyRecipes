"""Web search fallback for when a user has no URL or text to parse directly.

Wraps `ddgs.DDGS` (DuckDuckGo) so `app/main.py` stays free of the third-party
search API shape and has a single seam to mock in tests.
"""

from ddgs import DDGS

from app.schemas import WebSearchResult


def search_recipes_web(query: str, max_results: int = 3) -> list[WebSearchResult]:
    """Search the web for recipe pages matching `query`, returning the top results."""
    search_query = f"{query} recipe cooking"
    results = DDGS().text(search_query, max_results=max_results)
    return [
        WebSearchResult(title=r.get("title", ""), url=r.get("href", ""), snippet=r.get("body", ""))
        for r in results
    ]
