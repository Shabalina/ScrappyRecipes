# app/services/recipe_db_service.py
from typing import List, Tuple

from sqlalchemy import func, select
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

    async def delete_recipe(self, recipe_id: int) -> bool:
        """
        Deletes a recipe by id. Returns True if a row was deleted,
        False if no recipe with that id exists.
        """
        recipe = await self.db.get(RecipeModel, recipe_id)
        if recipe is None:
            return False

        await self.db.delete(recipe)
        await self.db.commit()
        return True

    async def list_recipes(self, skip: int, limit: int) -> Tuple[List[RecipeModel], int]:
        """
        Returns a page of recipes ordered by creation date descending,
        alongside the total row count for pagination.
        """
        total = await self.db.scalar(select(func.count()).select_from(RecipeModel))

        stmt = (
            select(RecipeModel)
            .order_by(RecipeModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        recipes = result.scalars().all()

        return recipes, total 