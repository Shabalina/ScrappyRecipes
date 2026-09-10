variable "environment" {
  description = "Deployment environment. Drives resource naming/tagging and which env-owns-shared-resources switches are set."
  type        = string
  default     = "qa"

  validation {
    condition     = contains(["qa", "prod"], var.environment)
    error_message = "environment must be either \"qa\" or \"prod\"."
  }
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Base name used to prefix/tag all resources, e.g. scrappy-recipes-qa."
  type        = string
  default     = "scrappy-recipes"
}

# --- ECR (shared across environments) ---

variable "create_ecr_repository" {
  description = "Whether this apply creates the shared ECR repository. Exactly one environment (qa) should set this true; the other(s) set it false and read the repository via data source instead, since ECR repository names must be unique per account/region."
  type        = bool
  default     = true
}

variable "ecr_untagged_image_expiry_days" {
  description = "Days after which untagged ECR images are expired by the lifecycle policy."
  type        = number
  default     = 14
}

variable "ecr_tagged_image_keep_count" {
  description = "Number of most recent tagged images (per environment tag prefix, qa-*/prod-*) to retain."
  type        = number
  default     = 10
}

# --- GitHub OIDC (shared across environments) ---

variable "create_github_oidc_provider" {
  description = "Whether this apply creates the GitHub Actions OIDC identity provider. Only one provider can exist per URL per AWS account, so exactly one environment (qa) should set this true; the other(s) set it false and reference the existing provider via data source."
  type        = bool
  default     = true
}

variable "github_org" {
  description = "GitHub organisation/user that owns the repository allowed to assume the CI/CD role."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name allowed to assume the CI/CD role."
  type        = string
}

variable "github_oidc_allowed_refs" {
  description = "Git ref claims (e.g. \"ref:refs/heads/main\") allowed to assume the GitHub Actions role for this environment."
  type        = list(string)
  default     = ["ref:refs/heads/main"]
}

# --- Lambda / IAM ---

variable "bedrock_llm_model_id" {
  description = "Bedrock model id used for text parsing/shopping-list consolidation (Claude 3.5 Haiku)."
  type        = string
  default     = "anthropic.claude-3-5-haiku-20241022-v1:0"
}

variable "bedrock_embedding_model_id" {
  description = "Bedrock model id used for embeddings (Titan Embed Text v2)."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "image_tag" {
  description = "ECR image tag the Lambda function deploys. CI pushes environment-specific tags (e.g. qa-<sha>, prod-<sha>)."
  type        = string
  default     = "qa-latest"
}

variable "lambda_memory_size" {
  description = "Lambda function memory allocation in MB."
  type        = number
  default     = 1024
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds."
  type        = number
  default     = 30
}

variable "ai_provider" {
  description = "AI_PROVIDER env var for the app. Bedrock is unconditional for text parsing/shopping-list; this only affects the embeddings opt-out."
  type        = string
  default     = "bedrock"
}

# --- Secrets — supply via a gitignored terraform.tfvars, never committed ---

variable "app_api_key" {
  description = "Shared X-API-Key secret checked by verify_api_key()."
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "Async SQLAlchemy DATABASE_URL for this environment's Postgres instance."
  type        = string
  sensitive   = true
}

variable "gemini_api_key" {
  description = "Gemini API key for image/vision parsing (always required regardless of AI_PROVIDER)."
  type        = string
  sensitive   = true
}
