"""BedrockService — Claude 3.5 Haiku parsing/consolidation and Titan embeddings,
with `boto3.client("bedrock-runtime")` stubbed. No AWS credentials or network calls.
"""

import json
from unittest.mock import MagicMock

import pytest

from app.schemas import RecipeCreate, ShoppingListResult


def _invoke_model_response(body: dict) -> dict:
    """Mimics the real `invoke_model` return shape: a dict with a StreamingBody-like `.read()`."""
    return {"body": MagicMock(read=MagicMock(return_value=json.dumps(body).encode("utf-8")))}


@pytest.fixture
def mock_boto_client(monkeypatch):
    """Stub `boto3.client("bedrock-runtime")`; the client is built in `__init__`."""
    import app.services.bedrock_service as bedrock_service

    client = MagicMock()
    monkeypatch.setattr(bedrock_service.boto3, "client", MagicMock(return_value=client))
    return client


@pytest.fixture
def service(mock_boto_client):
    from app.services.bedrock_service import BedrockService

    return BedrockService()


class TestGenerateEmbedding:
    async def test_returns_native_1024_dim_vector(self, service, mock_boto_client):
        mock_boto_client.invoke_model.return_value = _invoke_model_response(
            {"embedding": [0.1] * 1024}
        )

        vector = await service.generate_embedding("Title: Pancakes")

        assert len(vector) == 1024
        assert vector == [0.1] * 1024

    async def test_uses_titan_model_and_requests_1024_dims(self, service, mock_boto_client):
        mock_boto_client.invoke_model.return_value = _invoke_model_response(
            {"embedding": [0.0] * 1024}
        )

        await service.generate_embedding("Title: Pancakes")

        kwargs = mock_boto_client.invoke_model.call_args.kwargs
        assert kwargs["modelId"] == "amazon.titan-embed-text-v2:0"
        body = json.loads(kwargs["body"])
        assert body["inputText"] == "Title: Pancakes"
        assert body["dimensions"] == 1024


class TestParseTextRecipe:
    async def test_returns_validated_recipe(self, service, mock_boto_client, sample_recipe):
        mock_boto_client.invoke_model.return_value = _invoke_model_response(
            {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "extract_recipe",
                        "input": sample_recipe.model_dump(),
                    }
                ]
            }
        )

        recipe = await service.parse_text_recipe("2 cups flour, fry them up. Serves 4.")

        assert isinstance(recipe, RecipeCreate)
        assert recipe.title == sample_recipe.title
        assert recipe.servings == 4

    async def test_forces_the_extract_recipe_tool(self, service, mock_boto_client, sample_recipe):
        mock_boto_client.invoke_model.return_value = _invoke_model_response(
            {
                "content": [
                    {"type": "tool_use", "name": "extract_recipe", "input": sample_recipe.model_dump()}
                ]
            }
        )

        await service.parse_text_recipe("Grandma's messy blog text")

        kwargs = mock_boto_client.invoke_model.call_args.kwargs
        assert kwargs["modelId"] == "anthropic.claude-3-5-haiku-20241022-v1:0"
        body = json.loads(kwargs["body"])
        assert body["anthropic_version"] == "bedrock-2023-05-31"
        assert body["tool_choice"] == {"type": "tool", "name": "extract_recipe"}
        assert body["tools"][0]["name"] == "extract_recipe"
        assert "Grandma's messy blog text" in body["messages"][0]["content"]


class TestGenerateShoppingList:
    async def test_returns_validated_shopping_list(self, service, mock_boto_client):
        shopping_list = {
            "categories": [
                {
                    "category": "Produce",
                    "items": [
                        {
                            "item": "Onion",
                            "quantity": "2",
                            "unit": "medium",
                            "sources": ["Soup"],
                        }
                    ],
                }
            ]
        }
        mock_boto_client.invoke_model.return_value = _invoke_model_response(
            {
                "content": [
                    {"type": "tool_use", "name": "build_shopping_list", "input": shopping_list}
                ]
            }
        )

        recipe = MagicMock(title="Soup", ingredients=[{"name": "onion", "quantity": 2, "unit": "medium"}])
        result = await service.generate_shopping_list([recipe])

        assert isinstance(result, ShoppingListResult)
        assert result.categories[0].category == "Produce"
        assert result.categories[0].items[0].item == "Onion"

    async def test_forces_the_build_shopping_list_tool(self, service, mock_boto_client):
        mock_boto_client.invoke_model.return_value = _invoke_model_response(
            {"content": [{"type": "tool_use", "name": "build_shopping_list", "input": {"categories": []}}]}
        )

        recipe = MagicMock(title="Soup", ingredients=[{"name": "onion", "quantity": 2, "unit": "medium"}])
        await service.generate_shopping_list([recipe])

        kwargs = mock_boto_client.invoke_model.call_args.kwargs
        body = json.loads(kwargs["body"])
        assert body["tool_choice"] == {"type": "tool", "name": "build_shopping_list"}
        assert "Soup" in body["messages"][0]["content"]


class TestProviderDispatch:
    async def test_embedding_service_routes_to_bedrock(self, monkeypatch, mock_boto_client):
        monkeypatch.setenv("AI_PROVIDER", "bedrock")
        mock_boto_client.invoke_model.return_value = _invoke_model_response(
            {"embedding": [0.2] * 1024}
        )

        from app.services.embedding_service import generate_embedding

        vector = await generate_embedding("Title: Pancakes")

        assert len(vector) == 1024
        mock_boto_client.invoke_model.assert_called_once()

    async def test_parser_always_routes_text_parsing_to_bedrock(
        self, monkeypatch, mock_boto_client, sample_recipe
    ):
        """Text parsing has no other provider anymore — Claude on Bedrock is unconditional."""
        mock_boto_client.invoke_model.return_value = _invoke_model_response(
            {
                "content": [
                    {"type": "tool_use", "name": "extract_recipe", "input": sample_recipe.model_dump()}
                ]
            }
        )

        import app.services.llm_parser as llm_parser

        monkeypatch.setattr(llm_parser, "genai", MagicMock())
        parser = llm_parser.RecipeParserService()

        recipe = await parser.parse_text_recipe("anything")

        assert recipe.title == sample_recipe.title
        mock_boto_client.invoke_model.assert_called_once()
