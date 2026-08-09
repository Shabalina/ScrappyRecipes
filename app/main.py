from contextlib import asynccontextmanager
from typing import Annotated, List

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

load_dotenv()

from app.database import Base, engine, get_db
from app.models import RecipeModel
from app.schemas import ParseTextRequest, ParseUrlRequest, RecipeRead
from app.services.embedding_service import generate_embedding
from app.services.router_service import LLMRouterService

# --- 1. Lifespan Handler for DB Table Creation ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Executes on application startup:
    1. Enables pgvector extension in PostgreSQL.
    2. Creates missing database tables.
    """
    async with engine.begin() as conn:
        # Enable pgvector if using PostgreSQL with vector support
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Cleanup on shutdown
    await engine.dispose()


app = FastAPI(
    title="Recipe Extraction API",
    version="1.0.0",
    description="Extract structured JSON recipes from text, web URLs, or multi-page screenshot images.",
    lifespan=lifespan
)

# Initialize the LLM router service singleton
router_service = LLMRouterService()


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok", "service": "Recipe Extraction Engine"}


# --- Recipe Parsing Endpoints ---

@app.post(
    "/api/v1/recipes/parse-text", 
    response_model=RecipeRead, 
    status_code=status.HTTP_201_CREATED
)
async def parse_text(payload: ParseTextRequest, db: AsyncSession = Depends(get_db)):
    """Parse raw copied text and save to DB."""
    try:
        return await router_service.route_and_parse(raw_text=payload.text, db=db)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post(
    "/api/v1/recipes/parse-url", 
    response_model=RecipeRead, 
    status_code=status.HTTP_201_CREATED
)
async def parse_url(payload: ParseUrlRequest, db: AsyncSession = Depends(get_db)):
    """Scrape web URL, parse recipe, and save to DB."""
    try:
        return await router_service.route_and_parse(url=str(payload.url), db=db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"URL error: {str(e)}")


@app.post(
    "/api/v1/recipes/parse-images", 
    response_model=RecipeRead, 
    status_code=status.HTTP_201_CREATED
)
async def parse_images(
    files: Annotated[List[UploadFile], File(description="Recipe screenshots")],
    db: AsyncSession = Depends(get_db)
):
    """Parse screenshot images and save to DB."""
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one image required.")

    image_bytes_list = [await file.read() for file in files]
    mime_type = files[0].content_type or "image/jpeg"

    try:
        return await router_service.route_and_parse(
            image_bytes_list=image_bytes_list, 
            mime_type=mime_type, 
            db=db
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Image error: {str(e)}")


# --- Vector Search Endpoint ---

@app.get(
    "/api/v1/recipes/search", 
    response_model=List[RecipeRead], 
    status_code=status.HTTP_200_OK
)
async def search_recipes(
    q: str = Query(..., description="Natural language query (e.g. 'cold summer soup')"),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db)
):
    """Performs semantic vector similarity search across recipes using pgvector."""
    clean_query = q.strip()
    if not clean_query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Search query cannot be empty.")

    try:
        # 1. Convert search prompt into vector embedding
        query_vector = await generate_embedding(clean_query)

        # 2. Query DB using pgvector Cosine Distance (<=>)
        stmt = (
            select(RecipeModel)
            .where(RecipeModel.embedding.is_not(None))
            .order_by(RecipeModel.embedding.cosine_distance(query_vector))
            .limit(limit)
        )

        result = await db.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Search failed: {str(e)}")