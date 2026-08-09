# app/services/recipe_db_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import RecipeCreate
from app.models import RecipeModel
from app.services.embedding_service import generate_embedding, build_recipe_embedding_text

class RecipeDatabaseService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def save_parsed_recipe(self, recipe_data: RecipeCreate) -> RecipeModel:
        """
        Takes the Pydantic object from LLM parser, converts it 
        into a SQLAlchemy DB model, generates embeddings, and saves to Postgres.
        """
        # 1. Generate text & vector embedding for pgvector
        embed_text = build_recipe_embedding_text(recipe_data)
        vector = await generate_embedding(embed_text)

        # 2. Convert Pydantic model -> SQLAlchemy Database Model instance
        db_recipe = RecipeModel(
            title=recipe_data.title,
            description=recipe_data.description,
            prep_time_minutes=recipe_data.prep_time_minutes,
            cook_time_minutes=recipe_data.cook_time_minutes,
            servings=recipe_data.servings,
            # Serialize Pydantic sub-objects to dictionaries/JSON for SQL storage
            ingredients=[ing.model_dump() for ing in recipe_data.ingredients],
            instructions=recipe_data.instructions,
            cooking_methods=recipe_data.cooking_methods,
            tags=recipe_data.tags,
            embedding=vector  # Stored directly into the pgvector column!
        )

        # 3. Perform the DB operations (Insert & Commit)
        self.db.add(db_recipe)
        await self.db.commit()
        await self.db.refresh(db_recipe)

        return db_recipe 