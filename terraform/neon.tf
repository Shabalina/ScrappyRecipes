resource "neon_project" "scrappy_db" {
  name      = local.name_prefix
  region_id = var.aws_region
  pg_version = 16
  org_id     = var.neon_org_id

  branch {
    name          = "main"
    database_name = local.name_prefix
    role_name     = "recipe_admin"
  }
}
