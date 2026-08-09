# ScrappyRecipes

[FastAPI Endpoint] 
       │
       ▼
[LLMRouterService] ──(Checks tokens/source complexity)──► Assigns Model (Gemini or OpenAI)
       │
       ▼
[RecipeParserService] ──(Executes parsing with chosen model)──► Returns Unified Pydantic Output

text branch:

[Recipe URL] 
     │
     ▼ (Scraper Tool: e.g., HTTP requests + BeautifulSoup)
[Raw HTML String] 
     │
     ▼ (HTML Cleaner Utility)
[Stripped Markdown / Inner Text] (Removes scripts, navigation menus, and CSS)
     │
     ▼
[RecipeParserService.parse_text()] ──► Sent to LLM