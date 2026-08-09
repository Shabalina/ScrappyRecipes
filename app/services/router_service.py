from typing import List, Optional

from app.schemas import RecipeCreate
from app.services.llm_parser import RecipeParserService
from app.services.scraper_service import RecipeScraperService

class LLMRouterService:
    def __init__(self):
        # Instantiate the underlying parser service
        self.parser = RecipeParserService()
        # Instantiate the scraper service
        self.scraper = RecipeScraperService()

    async def route_and_parse(
        self,
        raw_text: Optional[str] = None,
        image_bytes_list: Optional[List[bytes]] = None,
        mime_type: str = "image/jpeg",
        url: Optional[str] = None,  # Added URL parameter
    ) -> RecipeCreate:
        """
        Dynamic Router Gatekeeper:
        - If URL provided              -> Scrapes HTML to clean text -> Routes to GPT-4o-Mini
        - If image bytes provided      -> Routes to Gemini Multimodal
        - If raw text provided         -> Routes to GPT-4o-Mini

        Returns an unsaved RecipeCreate draft. Persistence and embedding
        generation are deliberately NOT done here — the client reviews (and may
        edit) the draft, then POSTs it to /api/v1/recipes/confirm. This keeps
        embedding spend off drafts that are never approved.
        """
        parsed_recipe: RecipeCreate

        # 1. URL Route: Scrape page first, then pass cleaned text to OpenAI
        if url and url.strip():
            print(f"🔀 [Router]: Selected Route -> Web Scraper for URL: {url}")
            cleaned_text = await self.scraper.fetch_and_clean_html(url)
            parsed_recipe = await self.parser.parse_text_recipe(raw_text=cleaned_text)

        # 2. Multimodal Image Route
        elif image_bytes_list and len(image_bytes_list) > 0:
            print(f"🔀 [Router]: Selected Route -> Gemini 2.5 Flash ({len(image_bytes_list)} image page/s)")
            parsed_recipe = await self.parser.parse_images_recipe(
                image_bytes_list=image_bytes_list, 
                mime_type=mime_type
            )
        
        # 3. Fall back to lightweight text parsing if raw text is supplied
        elif raw_text and raw_text.strip():
            print("🔀 [Router]: Selected Route -> OpenAI GPT-4o-Mini (Text Input)")
            parsed_recipe = await self.parser.parse_text_recipe(raw_text=raw_text)

        else:
            # Raise value error if invalid payload provided
            raise ValueError("Invalid input payload: Neither valid text, URL, nor image bytes were provided to the router.")

        return parsed_recipe