import os
from typing import List
from google import genai
from google.genai import types
from openai import OpenAI
from app.schemas import RecipeCreate, ShoppingListResult

class RecipeParserService:
    def __init__(self):
        # The SDKs automatically look for GEMINI_API_KEY and OPENAI_API_KEY in env
        self.gemini_client = genai.Client()
        self.openai_client = OpenAI()

    async def parse_images_recipe(self, image_bytes_list: List[bytes], mime_type: str = "image/jpeg") -> RecipeCreate:
        """
        Route 1: Image Parsing via Gemini 1.5 Flash (Free Tier Multimodal)
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
        Route 2: Text Parsing via OpenAI GPT-4o-Mini (Ultra-low cost text handling)
        Converts scraped blog markdown or text into structured recipe schemas.
        """
        response = self.openai_client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are an expert culinary data extractor. Convert messy text into structured recipe schemas."
                },
                {
                    "role": "user", 
                    "content": f"Format this recipe: {raw_text}"
                }
            ],
            response_format=RecipeCreate,
        )
        
        return response.choices[0].message.parsed

    async def generate_shopping_list(self, recipes: List) -> ShoppingListResult:
        """
        Route 3: Shopping List Aggregation via OpenAI GPT-4o-Mini
        Consolidates ingredients from several recipes (each an object with
        `.title` and `.ingredients`, the latter a list of {name, quantity,
        unit} dicts) into a single grocery list, deduplicating equivalent
        items and grouping them into store sections.
        """
        recipes_text = "\n\n".join(
            f"Recipe: {recipe.title}\nIngredients: " + ", ".join(
                f"{ing['quantity']} {ing.get('unit') or ''} {ing['name']}".strip()
                for ing in recipe.ingredients
            )
            for recipe in recipes
        )

        response = self.openai_client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert grocery shopping assistant. Given ingredient lists "
                        "from several recipes, consolidate identical or equivalent items into a "
                        "single entry with a combined quantity, and group them into grocery "
                        "store sections such as Produce, Meat & Seafood, Dairy & Refrigerated, "
                        "Bakery, Pantry & Spices, and Other. For each item, list every recipe "
                        "title it came from."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Consolidate these recipes into a shopping list:\n\n{recipes_text}",
                },
            ],
            response_format=ShoppingListResult,
        )

        return response.choices[0].message.parsed