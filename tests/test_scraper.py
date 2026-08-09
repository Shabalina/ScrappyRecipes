"""RecipeScraperService — HTML cleaning and network failure handling.

Uses `httpx.MockTransport` rather than mocking the service's own methods, so the
real BeautifulSoup cleaning and the real `raise_for_status()` error path both
execute. No socket is opened.
"""

import httpx
import pytest

from app.services.scraper_service import RecipeScraperService


@pytest.fixture
def scrape(monkeypatch):
    """Returns `scrape(handler) -> cleaned_text`, routing httpx through a mock.

    Also records the client kwargs so tests can assert on transport settings.
    """
    import app.services.scraper_service as scraper_service

    recorded = {}
    # Bind the real class first: patching `scraper_service.httpx` mutates the
    # shared httpx module, so referring to httpx.AsyncClient inside the factory
    # would resolve back to the factory and recurse.
    real_async_client = httpx.AsyncClient

    def run(handler):
        def factory(**kwargs):
            recorded.update(kwargs)
            kwargs.pop("http2", None)  # irrelevant to MockTransport
            return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(scraper_service.httpx, "AsyncClient", factory)
        return RecipeScraperService().fetch_and_clean_html("https://example.com/recipe")

    run.recorded = recorded
    return run


def html_response(body: str, status: int = 200):
    return lambda *_: httpx.Response(status, html=body)


class TestHtmlCleaning:
    async def test_strips_noise_tags_and_keeps_content(self, scrape):
        page = """
        <html><head><style>.a{color:red}</style></head>
        <body>
          <nav>Home | About | Subscribe</nav>
          <header>Cooking Blog</header>
          <script>analytics('track');</script>
          <h1>Spinach Feta Burgers</h1>
          <p>1 lb ground turkey</p>
          <aside>Sponsored content</aside>
          <form><input name="email"></form>
          <noscript>Enable JavaScript</noscript>
          <iframe src="ad.html"></iframe>
          <footer>Copyright 2026</footer>
        </body></html>
        """

        text = await scrape(html_response(page))

        assert "Spinach Feta Burgers" in text
        assert "1 lb ground turkey" in text
        for noise in (
            "analytics",
            "color:red",
            "Subscribe",
            "Cooking Blog",
            "Sponsored content",
            "Enable JavaScript",
            "Copyright 2026",
        ):
            assert noise not in text, f"{noise!r} should have been stripped"

    async def test_collapses_blank_lines_and_trims(self, scrape):
        page = "<html><body><p>   Step one   </p>\n\n\n<p>Step two</p>   </body></html>"

        text = await scrape(html_response(page))

        assert text == "Step one\nStep two"

    async def test_empty_body_yields_empty_string(self, scrape):
        text = await scrape(html_response("<html><body></body></html>"))
        assert text == ""


class TestNetworkFailures:
    @pytest.mark.parametrize("status", [403, 404, 429, 500, 503])
    async def test_http_errors_become_actionable_value_error(self, scrape, status):
        with pytest.raises(ValueError, match="Could not access the website") as exc:
            await scrape(html_response("<html>blocked</html>", status=status))

        # The message is user-facing: it must suggest the paste/screenshot fallbacks.
        message = str(exc.value)
        assert "copy and paste" in message
        assert "screenshot" in message

    async def test_connection_timeout_becomes_value_error(self, scrape):
        def handler(request):
            raise httpx.ConnectTimeout("timed out", request=request)

        with pytest.raises(ValueError, match="Could not access the website"):
            await scrape(handler)

    async def test_dns_failure_becomes_value_error(self, scrape):
        def handler(request):
            raise httpx.ConnectError("name resolution failed", request=request)

        with pytest.raises(ValueError, match="Could not access the website"):
            await scrape(handler)

    async def test_original_error_is_chained_for_debugging(self, scrape):
        with pytest.raises(ValueError) as exc:
            await scrape(html_response("nope", status=403))

        assert isinstance(exc.value.__cause__, httpx.HTTPStatusError)


class TestRequestConfiguration:
    async def test_emulates_a_browser_and_follows_redirects(self, scrape):
        await scrape(html_response("<html><body><p>ok</p></body></html>"))

        assert scrape.recorded["follow_redirects"] is True
        assert scrape.recorded["timeout"] == 10.0

        user_agent = scrape.recorded["headers"]["User-Agent"]
        assert "Mozilla/5.0" in user_agent
        assert "Chrome/" in user_agent
