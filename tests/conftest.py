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

import app.services.bedrock_service as bedrock_service
from app.schemas import IngredientItem, RecipeCreate

TEST_API_KEY = "local_dev_secret_key_123"
API_KEY_HEADERS = {"X-API-Key": TEST_API_KEY}


# --------------------------------------------------------------------------
# Safety net
# --------------------------------------------------------------------------

def _unmocked_bedrock_client(*args, **kwargs):
    """Fails loudly if a test reaches BedrockService without stubbing boto3.

    AI_PROVIDER defaults to "bedrock" (app/core/config.py) and this host may
    have real, working AWS credentials — without this guard, a test missing
    its boto3 mock would silently place a live call to AWS Bedrock instead of
    failing. See `mock_boto_client` in tests/test_bedrock_service.py for the
    real stub.
    """
    raise RuntimeError(
        "boto3.client('bedrock-runtime') was called without a mock — this test is "
        "missing the mock_boto_client fixture (or an AI_PROVIDER override to a "
        "non-Bedrock provider)."
    )


@pytest.fixture(autouse=True)
def _no_live_api(monkeypatch):
    """Guarantee no test inherits real credentials from the developer's .env."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key-not-real")
    monkeypatch.setenv("APP_API_KEY", TEST_API_KEY)
    monkeypatch.setattr(bedrock_service.boto3, "client", _unmocked_bedrock_client)


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
def parser(monkeypatch, mock_gemini_generate):
    """A RecipeParserService with its Gemini client stubbed, for image-parsing tests.

    `gemini_client` is a lazy property (constructed on first access, not in
    `__init__`) — see app/services/llm_parser.py — so `genai` must be replaced
    before that first access, which is what accessing `service.gemini_client`
    below triggers. Text parsing/shopping-list generation always go through
    Bedrock now (no OpenAI opt-out); see tests/test_bedrock_service.py.
    """
    import app.services.llm_parser as llm_parser

    monkeypatch.setattr(llm_parser, "genai", MagicMock())

    service = llm_parser.RecipeParserService()
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
