#############################################
# IAM: memory execution role + application policy
#############################################

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ---- Memory execution role (assumed by the AgentCore Memory service) ----
data "aws_iam_policy_document" "memory_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    # Scope the trust to this account to avoid the confused-deputy problem.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "memory_execution" {
  count              = var.enable_memory_execution_role ? 1 : 0
  name               = "${var.name_prefix}-memory-exec"
  assume_role_policy = data.aws_iam_policy_document.memory_trust.json
  tags               = var.tags
}

# Minimal permissions the memory service needs to operate (e.g. long-term
# strategy processing). Short-term-only setups need very little; we keep it
# scoped and documented.
data "aws_iam_policy_document" "memory_execution" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:*"]
  }
}

resource "aws_iam_role_policy" "memory_execution" {
  count  = var.enable_memory_execution_role ? 1 : 0
  name   = "${var.name_prefix}-memory-exec-policy"
  role   = aws_iam_role.memory_execution[0].id
  policy = data.aws_iam_policy_document.memory_execution.json
}

# ---- Application policy (attach to whatever principal runs the agent) ----
# Grants exactly the APIs the redact-then-store app calls:
#   - bedrock:ApplyGuardrail       (the sanitize() filter)
#   - bedrock-agentcore memory R/W (add_turns / CreateEvent, retrieval)
#   - logs:PutLogEvents            (audit trail)
data "aws_iam_policy_document" "app" {
  statement {
    sid       = "ApplyGuardrail"
    effect    = "Allow"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = [aws_bedrock_guardrail.pii.guardrail_arn]
  }

  statement {
    sid    = "InvokeModel"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = ["arn:aws:bedrock:${data.aws_region.current.region}::foundation-model/*"]
  }

  statement {
    sid    = "AgentCoreMemory"
    effect = "Allow"
    actions = [
      "bedrock-agentcore:CreateEvent",
      "bedrock-agentcore:ListEvents",
      "bedrock-agentcore:GetEvent",
      "bedrock-agentcore:RetrieveMemoryRecords",
      "bedrock-agentcore:ListMemoryRecords",
      "bedrock-agentcore:GetMemoryRecord",
    ]
    resources = [awscc_bedrockagentcore_memory.short_term.memory_arn]
  }

  statement {
    sid    = "AuditLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = var.manage_audit_log_group ? ["${aws_cloudwatch_log_group.audit[0].arn}:*"] : ["arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:${var.audit_log_group_name}:*"]
  }
}

resource "aws_iam_policy" "app" {
  name        = "${var.name_prefix}-app-policy"
  description = "Permissions for the redact-then-store agent (ApplyGuardrail + AgentCore memory + audit logs)."
  policy      = data.aws_iam_policy_document.app.json
  tags        = var.tags
}
