import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Run this file directly from anywhere: put the project root on sys.path so
# `app` resolves, and anchor fixture paths to this directory instead of cwd.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
IMAGES_DIR = Path(__file__).resolve().parent.parent / "test_images"
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.router_service import LLMRouterService

# Load local .env file to expose GEMINI_API_KEY and OPENAI_API_KEY
load_dotenv(PROJECT_ROOT / ".env")

async def main():
    router = LLMRouterService()

    # Test 1: Route Text through Router
    print("--- Testing Router Text Route ---")
    sample_text = "Ingredients: 2 eggs, 1 cup milk, 1 cup flour. Steps: Mix well and fry on medium heat."
    recipe_from_text = await router.route_and_parse(raw_text=sample_text)
    print(f"Result Title: {recipe_from_text.title}")

    # Test 2: Route Image through Router
    print("\n--- Testing Router Image Route ---")
    try:
        with open(IMAGES_DIR / "recipe_page1.jpeg", "rb") as f1, open(IMAGES_DIR / "recipe_page2.jpeg", "rb") as f2:
            images = [f1.read(), f2.read()]
        recipe_from_img = await router.route_and_parse(image_bytes_list=images)
        print(f"Result Title: {recipe_from_img.title}")
    except FileNotFoundError:
        print(f"Skipped image test (fixtures not found in {IMAGES_DIR}).")

if __name__ == "__main__":
    asyncio.run(main())