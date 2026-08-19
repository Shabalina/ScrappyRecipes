"""Shared fixtures for the mocked test suite.

Nothing in `tests/` may touch the network or a real API key. The `_no_live_api`
autouse fixture below enforces that by planting dummy credentials, so a mock
that is accidentally missing fails on a stubbed client rather than quietly
billing a real request.

Opt-in live checks live in `tests/live/` (see that directory's docstrings).
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas import IngredientItem, RecipeCreate


# --------------------------------------------------------------------------
# Safety net
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_live_api(monkeypatch):
    """Guarantee no test inherits real credentials from the developer's .env."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key-not-real")


# --------------------------------------------------------------------------
# Sample data
# --------------------------------------------------------------------------

@pytest.fixture
def sample_recipe() -> RecipeCreate:
    """A fully-populated RecipeCreate, standing in for LLM output."""
    return RecipeCreate(
        title="Grandma's Quick Sunday Pancakes",
        description="Fluffy weekend pancakes.",
        prep_time_minutes=10,
        cook_time_minutes=15,
        servings=4,
        ingredients=[
            IngredientItem(name="all-purpose flour", quantity=2.0, unit="cups"),
            IngredientItem(name="white sugar", quantity=2.5, unit="tablespoons"),
            IngredientItem(name="whole milk", quantity=1.0, unit="cups"),
        ],
        instructions=["Mix the dry ingredients.", "Whisk in the milk.", "Fry until golden."],
        cooking_methods=["Frying"],
        tags=["Breakfast", "Kid-Friendly"],
    )


# --------------------------------------------------------------------------
# Stubbed LLM clients
# --------------------------------------------------------------------------

@pytest.fixture
def mock_openai_parse(sample_recipe):
    """Stub for `openai_client.beta.chat.completions.parse`.

    Mirrors the real return shape: `.choices[0].message.parsed` holds the
    already-validated Pydantic object. Note the SDK call is synchronous even
    though it sits inside an `async def`, so this is a MagicMock, not an
    AsyncMock — an AsyncMock here would return an un-awaited coroutine and the
    attribute chain would fail.
    """
    message = MagicMock()
    message.parsed = sample_recipe
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return MagicMock(return_value=response)


@pytest.fixture
def mock_gemini_generate(sample_recipe):
    """Stub for `gemini_client.models.generate_content`.

    The real SDK hands back raw JSON text which the service feeds to
    `RecipeCreate.model_validate_json`, so the stub must return a JSON *string* —
    this keeps the validation step under test rather than bypassing it.
    """
    response = MagicMock()
    response.text = sample_recipe.model_dump_json()
    return MagicMock(return_value=response)


@pytest.fixture
def parser(monkeypatch, mock_openai_parse, mock_gemini_generate):
    """A RecipeParserService whose two SDK clients are stubbed.

    `RecipeParserService.__init__` constructs `genai.Client()` and `OpenAI()`,
    both of which validate credentials eagerly, so they are replaced before the
    service is instantiated.
    """
    import app.services.llm_parser as llm_parser

    monkeypatch.setattr(llm_parser, "genai", MagicMock())
    monkeypatch.setattr(llm_parser, "OpenAI", MagicMock())

    service = llm_parser.RecipeParserService()
    service.openai_client.beta.chat.completions.parse = mock_openai_parse
    service.gemini_client.models.generate_content = mock_gemini_generate
    return service


@pytest.fixture
def mock_db_session():
    """An AsyncSession double: `add` is sync, the rest are awaited coroutines."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    return session
