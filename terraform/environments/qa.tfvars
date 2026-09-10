# QA environment. Owns the resources shared with prod (ECR repository, GitHub OIDC
# provider) — apply this environment first.

environment = "qa"
aws_region  = "eu-west-1"

create_ecr_repository       = true
create_github_oidc_provider = true

github_org  = "Shabalina"
github_repo = "ScrappyRecipes"
github_oidc_allowed_refs = [
  "ref:refs/heads/main",
  "ref:refs/heads/develop",
]

image_tag = "qa-latest"

lambda_memory_size = 1024
lambda_timeout     = 30
