import argparse
import asyncio
import os
import sys
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

# --- Configuration ---
# 1. Base administrative connection (connects to 'postgres' system DB to create target DB if missing)
USER = os.getenv("POSTGRES_USER", "postgres")
PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
HOST = os.getenv("POSTGRES_HOST", "localhost")
PORT = os.getenv("POSTGRES_PORT", "5432")
TARGET_DB_NAME = os.getenv("POSTGRES_DB", "scrappy_recipes")

DEFAULT_ADMIN_URL = f"postgresql+asyncpg://{USER}:{PASSWORD}@{HOST}:{PORT}/postgres"
DEFAULT_APP_URL = f"postgresql+asyncpg://{USER}:{PASSWORD}@{HOST}:{PORT}/{TARGET_DB_NAME}"

ADMIN_DB_URL = os.getenv("ADMIN_DATABASE_URL", DEFAULT_ADMIN_URL)
APP_DB_URL = os.getenv("DATABASE_URL", DEFAULT_APP_URL)

TARGET_DB_NAME = APP_DB_URL.split("/")[-1].split("?")[0]


async def ensure_database_and_extensions():
    """Checks if target database exists, creates it if not, and enables pgvector."""
    print(f"🔍 Checking if database '{TARGET_DB_NAME}' exists...")

    # Connect to system 'postgres' DB to perform administrative checks
    admin_engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")

    try:
        async with admin_engine.connect() as conn:
            result = await conn.execute(
                text(
                    f"SELECT 1 FROM pg_database WHERE datname='{TARGET_DB_NAME}'"
                )
            )
            exists = result.scalar()

            if not exists:
                print(f"⚡ Database '{TARGET_DB_NAME}' not found. Creating...")
                await conn.execute(text(f'CREATE DATABASE "{TARGET_DB_NAME}"'))
                print(f"✅ Database '{TARGET_DB_NAME}' created successfully.")
            else:
                print(f"✅ Database '{TARGET_DB_NAME}' already exists.")
    finally:
        await admin_engine.dispose()

    # Connect to the target application database to enable extensions
    print("🔌 Connecting to target database to check extensions...")
    app_engine = create_async_engine(APP_DB_URL)

    try:
        async with app_engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            print("✅ 'vector' extension is enabled.")
    except Exception as e:
        print(f"⚠️ Warning during extension creation: {e}")
    finally:
        await app_engine.dispose()

def _exec_alembic_upgrade():
    """Synchronous worker function to run Alembic command."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", APP_DB_URL)
    command.upgrade(alembic_cfg, "head")

async def run_alembic_migrations():
    """Runs Alembic migrations cleanly in a separate thread."""
    print("🚀 Running Alembic database migrations (upgrade head)...")
    try:
        await asyncio.to_thread(_exec_alembic_upgrade)
        print("✅ Migrations applied successfully.")
    except Exception as e:
        print(f"❌ Error applying migrations: {e}")
        sys.exit(1)

async def run_reembed():
    """Regenerates every recipe's embedding via Bedrock Titan v2 and overwrites it in place.

    Used after a dimension change (see the 2586f1c1d796 migration) to backfill
    rows whose embedding was nulled out by the schema change.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.models import RecipeModel
    from app.schemas import RecipeCreate
    from app.services.bedrock_service import BedrockService
    from app.services.embedding_service import build_recipe_embedding_text

    print("🔄 Re-embedding all recipes via Bedrock Titan v2...")
    engine = create_async_engine(APP_DB_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    bedrock = BedrockService()

    try:
        async with session_factory() as session:
            result = await session.execute(select(RecipeModel))
            recipes = result.scalars().all()
            print(f"Found {len(recipes)} recipe(s) to re-embed.")

            for recipe in recipes:
                draft = RecipeCreate.model_validate(recipe, from_attributes=True)
                text_to_embed = build_recipe_embedding_text(draft)
                recipe.embedding = await bedrock.generate_embedding(text_to_embed)
                print(f"  ✅ Re-embedded recipe #{recipe.id}: {recipe.title}")

            await session.commit()
        print("✅ Re-embedding complete.")
    except Exception as e:
        print(f"❌ Error re-embedding recipes: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()

async def main():
    parser = argparse.ArgumentParser(description="Automated Database Management Tool")
    parser.add_argument("--migrate", action="store_true", help="Run Alembic schema migrations.")
    parser.add_argument(
        "--reembed",
        action="store_true",
        help="Regenerate every recipe's embedding via Bedrock Titan v2 (real AWS calls).",
    )
    args = parser.parse_args()

    # Step 1: Ensure DB exists & vector extension is enabled
    await ensure_database_and_extensions()

    # Step 2: Run migrations
    if args.migrate:
        await run_alembic_migrations()
    else:
        print("ℹ️ Skipping migrations (--migrate flag not passed).")

    # Step 3: Re-embed existing recipes, if requested
    if args.reembed:
        await run_reembed()


if __name__ == "__main__":
    asyncio.run(main())