from sqlalchemy import Column, Integer, String, JSON, Text, DateTime, func
from pgvector.sqlalchemy import Vector
from app.database import Base

class RecipeModel(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    description = Column(Text, nullable=True)
    prep_time_minutes = Column(Integer, nullable=True)
    cook_time_minutes = Column(Integer, nullable=True)
    servings = Column(Integer, nullable=True)
    last_menu_number = Column(Integer, nullable=True)

    # Store complex nested fields as JSONB/JSON
    ingredients = Column(JSON, nullable=False)
    instructions = Column(JSON, nullable=False)
    cooking_methods = Column(JSON, default=[])
    tags = Column(JSON, default=[])

    # 💡 1536 dimensions corresponds to OpenAI text-embedding-3-small
    # For Gemini text-embedding-004, use 768
    embedding = Column(Vector(1536), nullable=True)


class MenuModel(Base):
    __tablename__ = "menus"

    id = Column(Integer, primary_key=True, index=True)
    menu_number = Column(Integer, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    recipe_ids = Column(JSON, nullable=False, default=list)