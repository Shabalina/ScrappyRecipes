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

async def main():
    parser = argparse.ArgumentParser(description="Automated Database Management Tool")
    parser.add_argument("--migrate", action="store_true", help="Run Alembic schema migrations.")
    args = parser.parse_args()

    # Step 1: Ensure DB exists & vector extension is enabled
    await ensure_database_and_extensions()

    # Step 2: Run migrations
    if args.migrate:
        await run_alembic_migrations()
    else:
        print("ℹ️ Skipping migrations (--migrate flag not passed).")


if __name__ == "__main__":
    asyncio.run(main())