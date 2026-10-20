output "guardrail_id" {
  description = "Guardrail identifier to pass to apply_guardrail."
  value       = aws_bedrock_guardrail.pii.guardrail_id
}

output "guardrail_arn" {
  description = "Guardrail ARN."
  value       = aws_bedrock_guardrail.pii.guardrail_arn
}

output "guardrail_version" {
  description = "Published guardrail version to pin (use \"DRAFT\" while iterating)."
  value       = aws_bedrock_guardrail_version.pii.version
}

output "memory_id" {
  description = "AgentCore Memory ID for MemorySessionManager."
  value       = awscc_bedrockagentcore_memory.short_term.memory_id
}

output "memory_arn" {
  description = "AgentCore Memory ARN."
  value       = awscc_bedrockagentcore_memory.short_term.memory_arn
}

output "audit_log_group" {
  description = "CloudWatch log group for redaction audit records."
  value       = var.manage_audit_log_group ? aws_cloudwatch_log_group.audit[0].name : var.audit_log_group_name
}

output "app_policy_arn" {
  description = "Attach this IAM policy to the principal that runs the agent."
  value       = aws_iam_policy.app.arn
}

# Convenience: ready-to-source environment block for the app.
output "env_file_contents" {
  description = "Copy this into app/.env (or run 'make env')."
  value       = <<-EOT
    AWS_REGION=${var.region}
    GUARDRAIL_ID=${aws_bedrock_guardrail.pii.guardrail_id}
    GUARDRAIL_VERSION=${aws_bedrock_guardrail_version.pii.version}
    MEMORY_ID=${awscc_bedrockagentcore_memory.short_term.memory_id}
    AUDIT_LOG_GROUP=${var.audit_log_group_name}
    ENABLE_CLOUDWATCH_AUDIT=${var.manage_audit_log_group}
  EOT
}
