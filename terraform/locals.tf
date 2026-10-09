locals {
  name_prefix = "${var.project_name}-${var.environment}"

  # Transform Neon's raw URL into SQLAlchemy asyncpg format:
  # postgresql://user:pass@host/db -> postgresql+asyncpg://user:pass@host/db?ssl=require
  neon_raw_url   = neon_project.scrappy_db.connection_uri_pooler
  neon_async_url = replace(
    replace(local.neon_raw_url, "postgres://", "postgresql+asyncpg://"),
    "postgresql://", "postgresql+asyncpg://"
  )

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
