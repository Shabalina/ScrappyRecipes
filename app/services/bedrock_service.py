import json
from typing import List

import boto3

from app.core.config import settings
from app.schemas import RecipeCreate, ShoppingListResult

# Titan Embed Text v2's native output size, matching `RecipeModel.embedding`
# (Vector(1024)) — OpenAI's text-embedding-3-small is requested with the same
# dimensions=1024 in embedding_service.py, so both providers are natively
# comparable in the same search index; no padding or truncation needed here.
TITAN_EMBEDDING_DIMENSIONS = 1024

RECIPE_TOOL = {
    "name": "extract_recipe",
    "description": "Extract structured recipe data from raw text.",
    "input_schema": RecipeCreate.model_json_schema(),
}

SHOPPING_LIST_TOOL = {
    "name": "build_shopping_list",
    "description": "Consolidate recipe ingredients into a categorized shopping list.",
    "input_schema": ShoppingListResult.model_json_schema(),
}


class BedrockService:
    """Amazon Bedrock adapter: Claude 3.5 Haiku for parsing/consolidation, Titan for embeddings.

    Selected via `AI_PROVIDER=bedrock` (app/core/config.py); Gemini/OpenAI
    remain the default and are unaffected.
    """

    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)

    def _invoke_claude_tool(self, system: str, user_content: str, tool: dict) -> dict:
        """
        Forces a single tool call so Claude's response is the tool's `input`
        object rather than prose — the Bedrock invoke_model equivalent of the
        OpenAI/Gemini structured-output routes in `llm_parser.py`.
        """
        response = self.client.invoke_model(
            modelId=settings.BEDROCK_LLM_MODEL_ID,
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4096,
                    "system": system,
                    "messages": [{"role": "user", "content": user_content}],
                    "tools": [tool],
                    "tool_choice": {"type": "tool", "name": tool["name"]},
                }
            ),
        )
        response_body = json.loads(response["body"].read())
        tool_use_block = next(
            block for block in response_body["content"] if block["type"] == "tool_use"
        )
        return tool_use_block["input"]

    async def parse_text_recipe(self, raw_text: str) -> RecipeCreate:
        """Recipe text parsing via Claude 3.5 Haiku on Bedrock."""
        result = self._invoke_claude_tool(
            system="You are an expert culinary data extractor. Convert messy text into structured recipe schemas.",
            user_content=f"Format this recipe: {raw_text}",
            tool=RECIPE_TOOL,
        )
        return RecipeCreate.model_validate(result)

    async def generate_shopping_list(self, recipes: List) -> ShoppingListResult:
        """Shopping list aggregation via Claude 3.5 Haiku on Bedrock."""
        recipes_text = "\n\n".join(
            f"Recipe: {recipe.title}\nIngredients: "
            + ", ".join(
                f"{ing['quantity']} {ing.get('unit') or ''} {ing['name']}".strip()
                for ing in recipe.ingredients
            )
            for recipe in recipes
        )

        result = self._invoke_claude_tool(
            system=(
                "You are an expert grocery shopping assistant. Given ingredient lists "
                "from several recipes, consolidate identical or equivalent items into a "
                "single entry with a combined quantity, and group them into grocery "
                "store sections such as Produce, Meat & Seafood, Dairy & Refrigerated, "
                "Bakery, Pantry & Spices, and Other. For each item, list every recipe "
                "title it came from."
            ),
            user_content=f"Consolidate these recipes into a shopping list:\n\n{recipes_text}",
            tool=SHOPPING_LIST_TOOL,
        )
        return ShoppingListResult.model_validate(result)

    async def generate_embedding(self, text: str) -> List[float]:
        """Generates a native 1024-dimensional Titan Embed Text v2 vector."""
        response = self.client.invoke_model(
            modelId=settings.BEDROCK_EMBEDDING_MODEL_ID,
            body=json.dumps({"inputText": text, "dimensions": TITAN_EMBEDDING_DIMENSIONS}),
        )
        response_body = json.loads(response["body"].read())
        return response_body["embedding"]
