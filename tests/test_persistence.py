"""Embedding construction and DB persistence.

These paths were untested by the old scripts, yet they decide what actually
lands in pgvector — a silently empty embedding degrades search to noise.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.embedding_service import build_recipe_embedding_text


class TestBuildRecipeEmbeddingText:
    """Pure function — no mocking required."""

    def test_includes_every_semantic_field(self, sample_recipe):
        text = build_recipe_embedding_text(sample_recipe)

        assert "Title: Grandma's Quick Sunday Pancakes" in text
        assert "Description: Fluffy weekend pancakes." in text
        assert "Ingredients: all-purpose flour, white sugar, whole milk" in text
        assert "Cooking Methods: Frying" in text
        assert "Tags: Breakfast, Kid-Friendly" in text

    def test_embeds_ingredient_names_without_quantities(self, sample_recipe):
        """Quantities are noise for semantic search; names carry the meaning."""
        text = build_recipe_embedding_text(sample_recipe)

        assert "2.0" not in text
        assert "cups" not in text

    def test_missing_description_does_not_render_none(self, sample_recipe):
        sample_recipe.description = None

        text = build_recipe_embedding_text(sample_recipe)

        assert "None" not in text
        assert "Description: \n" in text


class TestGenerateEmbedding:
    @pytest.fixture
    def mock_embeddings(self, monkeypatch):
        """Stub AsyncOpenAI; the client is built inside the function, so patch the class."""
        import app.services.embedding_service as embedding_service

        datum = MagicMock()
        datum.embedding = [0.1] * 1536
        response = MagicMock()
        response.data = [datum]

        create = AsyncMock(return_value=response)
        client = MagicMock()
        client.embeddings.create = create
        monkeypatch.setattr(
            embedding_service, "AsyncOpenAI", MagicMock(return_value=client)
        )
        return create

    async def test_returns_1536_dim_vector(self, mock_embeddings):
        from app.services.embedding_service import generate_embedding

        vector = await generate_embedding("Title: Pancakes")

        # Must match the Vector(1536) column in app/models.py or inserts fail.
        assert len(vector) == 1536
        assert all(isinstance(v, float) for v in vector)

    async def test_uses_the_expected_embedding_model(self, mock_embeddings):
        from app.services.embedding_service import generate_embedding

        await generate_embedding("Title: Pancakes")

        kwargs = mock_embeddings.await_args.kwargs
        assert kwargs["model"] == "text-embedding-3-small"
        assert kwargs["input"] == "Title: Pancakes"


class TestSaveParsedRecipe:
    @pytest.fixture
    def db_service(self, monkeypatch, mock_db_session):
        import app.services.recipe_db_service as recipe_db_service

        monkeypatch.setattr(
            recipe_db_service, "generate_embedding", AsyncMock(return_value=[0.5] * 1536)
        )
        return recipe_db_service.RecipeDatabaseService(mock_db_session)

    async def test_commits_the_row_with_its_embedding(
        self, db_service, mock_db_session, sample_recipe
    ):
        await db_service.save_parsed_recipe(sample_recipe)

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once()

        row = mock_db_session.add.call_args.args[0]
        assert row.title == sample_recipe.title
        assert len(row.embedding) == 1536

    async def test_serialises_ingredients_to_plain_dicts(
        self, db_service, mock_db_session, sample_recipe
    ):
        """Pydantic objects are not JSON-serialisable by the DB driver."""
        await db_service.save_parsed_recipe(sample_recipe)

        row = mock_db_session.add.call_args.args[0]
        assert all(isinstance(ing, dict) for ing in row.ingredients)
        assert row.ingredients[0] == {
            "name": "all-purpose flour",
            "quantity": 2.0,
            "unit": "cups",
        }
