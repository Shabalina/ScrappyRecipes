from typing import List
from google import genai
from google.genai import types
from app.schemas import RecipeCreate, ShoppingListResult

class RecipeParserService:
    """Image parsing via Gemini; text parsing & shopping-list consolidation via Claude on Bedrock."""

    def __init__(self):
        self._gemini_client = None
        self._bedrock_service = None

    @property
    def gemini_client(self):
        # Lazy: only constructed when image parsing is actually invoked, so a
        # Bedrock-only deployment with no GEMINI_API_KEY doesn't crash at startup.
        if self._gemini_client is None:
            self._gemini_client = genai.Client()
        return self._gemini_client

    @property
    def bedrock_service(self):
        if self._bedrock_service is None:
            from app.services.bedrock_service import BedrockService
            self._bedrock_service = BedrockService()
        return self._bedrock_service

    async def parse_images_recipe(self, image_bytes_list: List[bytes], mime_type: str = "image/jpeg") -> RecipeCreate:
        """
        Image Parsing via Gemini (multimodal)
        Accepts a list of image bytes to support multi-page screenshots/images
        and bundles them into a single structured schema.
        """
        contents = []

        # Convert all incoming images into standard Gemini parts
        for img_bytes in image_bytes_list:
            image_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
            contents.append(image_part)

        # Append the context extraction instruction to the payload array
        prompt = (
            "Analyze all provided image pages together. They represent a single recipe "
            "spanning multiple pages. Extract the title, list of ingredients with "
            "accurate quantities, step-by-step cooking instructions, cooking methods, "
            "and relevant search tags."
        )
        contents.append(prompt)

        # Request a strict structured JSON back from Gemini matching the schema
        response = self.gemini_client.models.generate_content(
            model='gemini-3.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RecipeCreate,
                temperature=0.1,  # Low temperature forces highly deterministic extraction
            ),
        )

        # Parse and return type-safe data verified by your schema
        return RecipeCreate.model_validate_json(response.text)

    async def parse_text_recipe(self, raw_text: str) -> RecipeCreate:
        """
        Text parsing via Claude 3.5 Haiku on Bedrock.
        Converts scraped blog markdown or text into structured recipe schemas.
        """
        return await self.bedrock_service.parse_text_recipe(raw_text)

    async def generate_shopping_list(self, recipes: List) -> ShoppingListResult:
        """
        Shopping list aggregation via Claude 3.5 Haiku on Bedrock.
        Consolidates ingredients from several recipes (each an object with
        `.title` and `.ingredients`, the latter a list of {name, quantity,
        unit} dicts) into a single grocery list, deduplicating equivalent
        items and grouping them into store sections.
        """
        return await self.bedrock_service.generate_shopping_list(recipes)
