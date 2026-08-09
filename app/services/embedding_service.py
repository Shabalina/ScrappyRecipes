import os
from typing import List
from openai import AsyncOpenAI
from app.schemas import RecipeCreate

def build_recipe_embedding_text(recipe: RecipeCreate) -> str:
    """
    Flattens a structured recipe into a dense semantic string 
    optimized for embedding models.
    """
    ingredients_str = ", ".join([ing.name for ing in recipe.ingredients])
    methods_str = ", ".join(recipe.cooking_methods)
    tags_str = ", ".join(recipe.tags)
    
    text_to_embed = (
        f"Title: {recipe.title}\n"
        f"Description: {recipe.description or ''}\n"
        f"Ingredients: {ingredients_str}\n"
        f"Cooking Methods: {methods_str}\n"
        f"Tags: {tags_str}"
    )
    return text_to_embed


async def generate_embedding(text: str) -> List[float]:
    """
    Generates a 1536-dimensional vector embedding using OpenAI text-embedding-3-small.
    """
    # Instantiate client dynamically to ensure environment variables are loaded
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding