resource "terraform_data" "workspace_guard" {
  lifecycle {
    precondition {
      condition     = terraform.workspace == var.environment
      error_message = "❌ Environment mismatch! Active workspace is '${terraform.workspace}', but var.environment is '${var.environment}'. Switch workspace using 'terraform workspace select ${var.environment}'."
    }
  }
}
