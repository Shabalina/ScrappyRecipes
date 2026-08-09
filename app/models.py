from sqlalchemy import Column, Integer, String, JSON, Text
from pgvector.sqlalchemy import Vector
from app.database import Base

class RecipeModel(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    prep_time_minutes = Column(Integer, nullable=True)
    cook_time_minutes = Column(Integer, nullable=True)
    servings = Column(Integer, nullable=True)
    
    # Store complex nested fields as JSONB/JSON
    ingredients = Column(JSON, nullable=False)
    instructions = Column(JSON, nullable=False)
    cooking_methods = Column(JSON, default=[])
    tags = Column(JSON, default=[])

    # 💡 1536 dimensions corresponds to OpenAI text-embedding-3-small
    # For Gemini text-embedding-004, use 768
    embedding = Column(Vector(1536), nullable=True)