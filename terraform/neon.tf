resource "neon_project" "scrappy_db" {
  name      = local.name_prefix
  region_id = "aws-${var.aws_region}"
  pg_version = 16
  org_id     = var.neon_org_id
  history_retention_seconds = 21600 # Max allowed on the Neon Free tier (6 hours)

  branch {
    name          = "main"
    database_name = local.name_prefix
    role_name     = "recipe_admin"
  }
}
