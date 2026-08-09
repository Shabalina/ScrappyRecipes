import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Run this file directly from anywhere: put the project root on sys.path so
# `app` resolves, regardless of cwd.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from app.services.router_service import LLMRouterService

async def main():
    router = LLMRouterService()
    
    # Test with a real public recipe URL
    test_url = "https://www.allrecipes.com/recipe/158968/spinach-and-feta-turkey-burgers/"
    
    print(f"--- Testing URL Route for: {test_url} ---")
    try:
        recipe = await router.route_and_parse(url=test_url)
        print("✅ URL Scraping & Parsing Success!")
        print(f"Title: {recipe.title}")
        print(f"Servings: {recipe.servings}")
        print(f"Ingredients extracted: {len(recipe.ingredients)}")
        print(f"Instruction steps: {len(recipe.instructions)}")
    except Exception as e:
        print(f"❌ URL Route Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())