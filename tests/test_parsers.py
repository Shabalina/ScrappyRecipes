"""RecipeParserService — image parsing (Gemini), with the SDK client stubbed.

Replaces the former print-based script: these assert on the request the service
builds and the object it returns, so a regression fails the run.

Text parsing and shopping-list consolidation always go through Claude on
Bedrock now (no OpenAI opt-out) — that behavior is covered in
tests/test_bedrock_service.py instead.
"""

from app.schemas import RecipeCreate


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
