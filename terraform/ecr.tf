# Shared ECR repository. Only the qa environment (create_ecr_repository = true) creates
# it; the prod apply reads the same repository via data source so both environments push
# to and deploy from one repo, distinguished by image tag (qa-*, prod-*).

resource "aws_ecr_repository" "app" {
  count = var.create_ecr_repository ? 1 : 0

  name                 = var.project_name
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

data "aws_ecr_repository" "app" {
  count = var.create_ecr_repository ? 0 : 1

  name = var.project_name
}

locals {
  ecr_repository_url = var.create_ecr_repository ? aws_ecr_repository.app[0].repository_url : data.aws_ecr_repository.app[0].repository_url
  ecr_repository_arn = var.create_ecr_repository ? aws_ecr_repository.app[0].arn : data.aws_ecr_repository.app[0].arn
}

resource "aws_ecr_lifecycle_policy" "app" {
  count = var.create_ecr_repository ? 1 : 0

  repository = aws_ecr_repository.app[0].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after ${var.ecr_untagged_image_expiry_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.ecr_untagged_image_expiry_days
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep last ${var.ecr_tagged_image_keep_count} qa-tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["qa"]
          countType     = "imageCountMoreThan"
          countNumber   = var.ecr_tagged_image_keep_count
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 3
        description  = "Keep last ${var.ecr_tagged_image_keep_count} prod-tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["prod"]
          countType     = "imageCountMoreThan"
          countNumber   = var.ecr_tagged_image_keep_count
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
