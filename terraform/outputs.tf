output "ecr_repository_url" {
  description = "URL of the shared ECR repository images are pushed to."
  value       = local.ecr_repository_url
}

output "github_actions_role_arn" {
  description = "IAM role ARN GitHub Actions assumes via OIDC to push images and trigger Lambda deployments for this environment."
  value       = aws_iam_role.github_actions.arn
}

output "api_gateway_url" {
  description = "Public HTTPS endpoint for the API Gateway HTTP API in front of the Lambda function."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "lambda_function_name" {
  description = "Name of the deployed Lambda function, used by CI to trigger code updates (lambda:UpdateFunctionCode)."
  value       = aws_lambda_function.app.function_name
}

output "lambda_function_arn" {
  description = "ARN of the deployed Lambda function."
  value       = aws_lambda_function.app.arn
}
