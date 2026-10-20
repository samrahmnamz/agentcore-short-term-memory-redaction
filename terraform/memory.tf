#############################################
# AgentCore short-term Memory + audit log group
#############################################

# Short-term memory store. No long-term strategies are configured here on
# purpose: this pattern is specifically about keeping raw PII out of the
# IMMUTABLE short-term event log, so we sanitize BEFORE add_turns/CreateEvent.
#
# memory_execution_role_arn is only required for long-term / custom strategies
# (where AgentCore invokes a model on your behalf). For short-term-only memory
# it is omitted, which also avoids the service's trust-policy validation.
resource "awscc_bedrockagentcore_memory" "short_term" {
  name                  = replace("${var.name_prefix}_stm", "-", "_")
  description           = "Short-term memory for the redact-then-store pattern."
  event_expiry_duration = var.event_expiry_days

  memory_execution_role_arn = var.enable_memory_execution_role ? aws_iam_role.memory_execution[0].arn : null

  tags = var.tags
}

# CloudWatch log group that the sanitizer middleware writes redaction
# decisions to for compliance auditing. Optional: skip if the deploying
# principal cannot create log groups.
resource "aws_cloudwatch_log_group" "audit" {
  count             = var.manage_audit_log_group ? 1 : 0
  name              = var.audit_log_group_name
  retention_in_days = var.audit_log_retention_days
  tags              = var.tags
}
