import os
from typing import AsyncGenerator
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

load_dotenv()

# 1. Fetch Database URL from Environment
DEFAULT_DEV_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/scrappy_recipes"

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DEV_URL)

# 2. Configure Async Engine
# If using SQLite locally, `check_same_thread=False` is needed
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True if you want to see raw SQL queries in console
    future=True,
    **engine_kwargs
)

# 3. Create Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# 4. Declarative Base for Models
Base = declarative_base()


# 5. Dependency Injection for FastAPI Endpoints
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session per request 
    and closes it cleanly after the response is sent.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()