# --- Execution role: permissions the running app itself needs at request time ---

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${local.name_prefix}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_exec_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Scoped to exactly the two foundation models the app calls (bedrock_service.py) —
# Titan Embed Text v2 for embeddings, the Claude 3.5 Haiku family for parsing/
# shopping-list — rather than "bedrock:InvokeModel" on "*".
data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid     = "BedrockInvokeModel"
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}",
      "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-3-5-haiku-*",
    ]
  }
}

resource "aws_iam_role_policy" "lambda_exec_bedrock" {
  name   = "${local.name_prefix}-bedrock-invoke"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.bedrock_invoke.json
}

# --- Function ---

resource "aws_lambda_function" "app" {
  function_name = local.name_prefix
  role          = aws_iam_role.lambda_exec.arn

  package_type = "Image"
  image_uri    = "${local.ecr_repository_url}:${var.image_tag}"

  memory_size = var.lambda_memory_size
  timeout     = var.lambda_timeout

  environment {
    variables = {
      AI_PROVIDER    = var.ai_provider
      AWS_REGION     = var.aws_region
      APP_API_KEY    = var.app_api_key
      DATABASE_URL   = var.database_url
      GEMINI_API_KEY = var.gemini_api_key
    }
  }

  tags = local.common_tags
}

# --- API Gateway HTTP API v2 (catch-all proxy in front of the Lambda) ---

resource "aws_apigatewayv2_api" "http_api" {
  name          = local.name_prefix
  protocol_type = "HTTP"

  tags = local.common_tags
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true

  tags = local.common_tags
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.app.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_lambda_permission" "apigateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.app.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}
