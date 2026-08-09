import asyncio
import os
from dotenv import load_dotenv
from app.schemas import RecipeCreate
# Assuming your consolidation file is named 'parser_service.py' inside app/services/
from app.services.llm_parser import RecipeParserService

# Load local .env file to expose GEMINI_API_KEY and OPENAI_API_KEY
load_dotenv()

async def test_text_parser(parser: RecipeParserService):
    print("\n--- Testing OpenAI Text Parser (gpt-4o-mini) ---")
    
    # Mock messy recipe text (simulating scraped blog context)
    messy_text = """
    Grandma's Quick Sunday Pancakes! 
    Hey guys, today I am making pancakes. You will need two cups of all-purpose flour, 
    2.5 tablespoons of white sugar, and 1 cup of whole milk. Just mix everything in a 
    bowl and fry them up on a hot stovetop skillet until golden brown. Makes 4 servings. 
    Great for breakfast and kid-friendly!
    """
    
    try:
        recipe: RecipeCreate = await parser.parse_text_recipe(messy_text)
        print("✅ OpenAI Text Parsing Success!")
        print(f"Title: {recipe.title}")
        print(f"Servings: {recipe.servings}")
        print(f"Ingredients: {recipe.ingredients}")
        print(f"Cooking Methods: {recipe.cooking_methods}")
    except Exception as e:
        print(f"❌ OpenAI Text Parsing Failed: {e}")

async def test_image_parser(parser: RecipeParserService):
    print("\n--- Testing Gemini Multi-Image Parser (gemini-1.5-flash) ---")
    
    # 1. Define the paths for your multi-page recipe screenshots
    image_paths = ["test_images/recipe_page1.jpeg", "test_images/recipe_page2.jpeg"]
    image_bytes_list = []

    # 2. Loop through and read the bytes for each image file
    for path in image_paths:
        if not os.path.exists(path):
            print(f"⚠️ Skipping image test: Missing '{path}'. Please add it to test multi-page parsing.")
            return
            
        with open(path, "rb") as f:
            image_bytes_list.append(f.read())

    print(f"📸 Loaded {len(image_bytes_list)} image pages. Sending to Gemini...")

    try:
        # 3. Pass the entire list of image bytes directly to your service
        recipe: RecipeCreate = await parser.parse_images_recipe(
            image_bytes_list=image_bytes_list, 
            mime_type="image/jpeg"
        )
        
        print("✅ Gemini Multi-Image Parsing Success!")
        print(f"Title: {recipe.title}")
        print(f"Ingredients extracted: {len(recipe.ingredients)} items found.")
        print(f"Total instruction steps: {len(recipe.instructions)}")
        print(f"Cooking Methods detected: {recipe.cooking_methods}")
        
    except Exception as e:
        print(f"❌ Gemini Image Parsing Failed: {e}")

async def main():
    # Pre-flight API check
    if not os.getenv("OPENAI_API_KEY") or not os.getenv("GEMINI_API_KEY"):
        print("❌ Error: Missing API Keys in environment! Check your .env file.")
        return

    # Instantiate the unified service
    parser_service = RecipeParserService()
    
    # Run tests sequentially
    await test_text_parser(parser_service)
    await test_image_parser(parser_service)

if __name__ == "__main__":
    # Standard entry point loop execution block
    asyncio.run(main())