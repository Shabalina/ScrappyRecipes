# Live API checks (opt-in, costs money)

These scripts hit the **real** OpenAI and Gemini APIs and make **real** network
requests. They are deliberately *not* part of the pytest suite:

* Named `check_*.py`, so pytest never auto-collects them.
* `tests/live` is listed in `norecursedirs` in `pytest.ini`.

The mocked suite in `tests/` covers the same code paths for free. Reach for these
only to confirm real credentials, billing, and model availability — e.g. after a
payment problem, an API-key rotation, or a model deprecation.

```bash
venv/bin/python tests/live/check_parsers.py   # OpenAI text + Gemini multi-image
venv/bin/python tests/live/check_router.py    # router dispatch, text + image
venv/bin/python tests/live/check_scraper.py   # live URL scrape -> parse
```

Requires `OPENAI_API_KEY` and `GEMINI_API_KEY` in the repo-root `.env`.

> ⚠️ These report failures as printed `❌` lines and still exit `0`. Read the
> output — do not rely on the exit status.
