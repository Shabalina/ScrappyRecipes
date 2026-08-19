from typing import List, Optional
from pydantic import BaseModel, Field

class IngredientItem(BaseModel):
    name: str = Field(description="The clean name of the ingredient, e.g., 'olive oil' or 'brown sugar'.")
    quantity: float = Field(description="The numerical amount needed, e.g., 2.5 or 100. Use decimals for fractions.")
    unit: Optional[str] = Field(None, description="The unit of measurement, e.g., 'tbsp', 'grams', 'cups', or 'units' if countable.")

class RecipeCreate(BaseModel):
    title: str = Field(description="The catchy, clean title of the recipe.")
    description: Optional[str] = Field(None, description="A brief summary or back-story of the dish.")
    prep_time_minutes: Optional[int] = Field(None, description="Preparation time in minutes.")
    cook_time_minutes: Optional[int] = Field(None, description="Cooking time in minutes.")
    servings: Optional[int] = Field(None, description="Number of portions this recipe makes.")
    
    # Nested lists force the LLM to structure components cleanly
    ingredients: List[IngredientItem] = Field(description="Complete list of all ingredients required.")
    instructions: List[str] = Field(description="Step-by-step ordered list of clear cooking instructions.")
    
    cooking_methods: List[str] = Field(
        default=[], 
        description="List of core methods used, e.g., ['Baking', 'Frying', 'Slow Cooking']."
    )
    tags: List[str] = Field(
        default=[], 
        description="Search optimization keywords, e.g., ['Gluten-Free', 'Dinner', 'Italian']."
    )

class RecipeRead(RecipeCreate):
    """A persisted recipe as returned to clients.

    The pgvector `embedding` column is deliberately NOT exposed: it is 1536
    floats (~25KB of JSON) per row, no client consumes it, and including it in
    list responses like /search multiplies payload size for no benefit.
    """
    id: int

    class Config:
        from_attributes = True

class RecipeSearchResult(RecipeRead):
    """A search hit: a persisted recipe plus its cosine distance to the query."""
    distance: float = Field(description="Cosine distance to the query embedding (0=identical, 2=opposite).")

class RecipeListResponse(BaseModel):
    """A page of the recipe library, sorted by creation date descending."""
    items: List[RecipeRead]
    total: int
    page: int
    limit: int

class ParseTextRequest(BaseModel):
    text: str = Field(..., description="Raw copied recipe text to parse.")

class ParseUrlRequest(BaseModel):
    url: str = Field(..., description="Web page URL containing a recipe to scrape and parse.")

class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str