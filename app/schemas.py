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
    id: int
    # Optional list of floats representing the vector (e.g. 1536 numbers for OpenAI)
    embedding: Optional[List[float]] = Field(
        None, 
        description="Vector representation for semantic search and RAG retrieval."
    )

    class Config:
        from_attributes = True

class ParseTextRequest(BaseModel):
    text: str = Field(..., description="Raw copied recipe text to parse.")

class ParseUrlRequest(BaseModel):
    url: str = Field(..., description="Web page URL containing a recipe to scrape and parse.")