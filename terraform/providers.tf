terraform {
  required_version = ">= 1.5.0"

  backend "s3" {
    bucket         = "terraform-state-bucket-sha" # or your dedicated state bucket
    key            = "scrappy-recipes/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-lock"
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}
