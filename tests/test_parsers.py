"""RecipeParserService — the two LLM extraction routes, with SDK clients stubbed.

Replaces the former print-based script: these assert on the request the service
builds and the object it returns, so a regression fails the run.
"""

from app.schemas import RecipeCreate


class TestParseTextRecipe:
    async def test_returns_validated_recipe(self, parser, sample_recipe):
        recipe = await parser.parse_text_recipe("2 cups flour, fry them up. Serves 4.")

        assert isinstance(recipe, RecipeCreate)
        assert recipe.title == sample_recipe.title
        assert recipe.servings == 4
        assert [i.name for i in recipe.ingredients] == [
            "all-purpose flour",
            "white sugar",
            "whole milk",
        ]

    async def test_sends_raw_text_and_schema_to_model(self, parser, mock_openai_parse):
        await parser.parse_text_recipe("Grandma's messy blog text")

        mock_openai_parse.assert_called_once()
        kwargs = mock_openai_parse.call_args.kwargs

        assert kwargs["model"] == "gpt-4o-mini"
        # The schema drives structured output; losing it silently degrades to prose.
        assert kwargs["response_format"] is RecipeCreate

        roles = [m["role"] for m in kwargs["messages"]]
        assert roles == ["system", "user"]
        assert "Grandma's messy blog text" in kwargs["messages"][1]["content"]

    async def test_ingredient_quantities_survive_as_floats(self, parser):
        recipe = await parser.parse_text_recipe("anything")

        sugar = next(i for i in recipe.ingredients if i.name == "white sugar")
        assert sugar.quantity == 2.5
        assert isinstance(sugar.quantity, float)


class TestParseImagesRecipe:
    async def test_returns_validated_recipe(self, parser, sample_recipe):
        recipe = await parser.parse_images_recipe([b"fake-jpeg-bytes"])

        assert isinstance(recipe, RecipeCreate)
        assert recipe.title == sample_recipe.title

    async def test_bundles_every_page_into_one_request(self, parser, mock_gemini_generate):
        pages = [b"page-one-bytes", b"page-two-bytes", b"page-three-bytes"]

        await parser.parse_images_recipe(pages)

        # One call, not one per page — the pages form a single multi-page recipe.
        mock_gemini_generate.assert_called_once()
        contents = mock_gemini_generate.call_args.kwargs["contents"]

        # N image parts plus exactly one trailing text prompt.
        assert len(contents) == len(pages) + 1
        assert isinstance(contents[-1], str)
        assert "image pages" in contents[-1]

    async def test_requests_structured_json_output(self, parser, mock_gemini_generate):
        await parser.parse_images_recipe([b"bytes"])

        kwargs = mock_gemini_generate.call_args.kwargs
        assert kwargs["model"] == "gemini-3.5-flash"

        config = kwargs["config"]
        assert config.response_mime_type == "application/json"
        assert config.response_schema is RecipeCreate
        # Low temperature is deliberate: extraction should be near-deterministic.
        assert config.temperature == 0.1

    async def test_passes_mime_type_through(self, parser, monkeypatch):
        """A PNG upload must not be relabelled as JPEG on the way to Gemini."""
        captured = []

        import app.services.llm_parser as llm_parser

        real_from_bytes = llm_parser.types.Part.from_bytes

        def spy(*, data, mime_type):
            captured.append(mime_type)
            return real_from_bytes(data=data, mime_type=mime_type)

        monkeypatch.setattr(llm_parser.types.Part, "from_bytes", spy)

        await parser.parse_images_recipe([b"a", b"b"], mime_type="image/png")

        assert captured == ["image/png", "image/png"]

    async def test_malformed_model_output_raises(self, parser, mock_gemini_generate):
        """Invalid JSON from the model must surface, not yield a half-built recipe."""
        import pydantic
        import pytest

        mock_gemini_generate.return_value.text = '{"title": "Missing everything else"}'

        with pytest.raises(pydantic.ValidationError):
            await parser.parse_images_recipe([b"bytes"])
