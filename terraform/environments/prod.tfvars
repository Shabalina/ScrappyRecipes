# Prod environment. Reads the shared resources qa owns (ECR repository, GitHub OIDC
# provider) via data source instead of recreating them — apply qa first.

environment = "prod"
aws_region  = "us-east-1"

create_ecr_repository       = false
create_github_oidc_provider = false

github_org  = "Shabalina"
github_repo = "ScrappyRecipes"
github_oidc_allowed_refs = [
  "ref:refs/heads/main",
]

image_tag = "prod-latest"

lambda_memory_size = 1024
lambda_timeout     = 30
