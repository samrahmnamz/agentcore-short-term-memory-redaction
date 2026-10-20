output "block_guardrail_id" {
  description = "Guardrail that BLOCKS SSN (default)."
  value       = aws_bedrock_guardrail.pii["block"].guardrail_id
}

output "mask_guardrail_id" {
  description = "Guardrail that MASKS (anonymizes) SSN."
  value       = aws_bedrock_guardrail.pii["mask"].guardrail_id
}

output "block_guardrail_version" {
  value = aws_bedrock_guardrail_version.pii["block"].version
}

output "mask_guardrail_version" {
  value = aws_bedrock_guardrail_version.pii["mask"].version
}

output "memory_id" {
  description = "AgentCore Memory ID for MemorySessionManager."
  value       = awscc_bedrockagentcore_memory.short_term.memory_id
}

output "memory_arn" {
  description = "AgentCore Memory ARN."
  value       = awscc_bedrockagentcore_memory.short_term.memory_arn
}

output "app_policy_arn" {
  description = "Attach this IAM policy to the principal that runs the agent."
  value       = aws_iam_policy.app.arn
}

# Convenience: ready-to-source environment block for the app.
# GUARDRAIL_ID defaults to the BLOCK guardrail; the *-mask make targets override
# it with GUARDRAIL_ID_MASK.
output "env_file_contents" {
  description = "Copy this into app/.env (or run 'make env')."
  value       = <<-EOT
    AWS_REGION=${var.region}
    MEMORY_ID=${awscc_bedrockagentcore_memory.short_term.memory_id}

    # SSN is BLOCKED (default)
    GUARDRAIL_ID=${aws_bedrock_guardrail.pii["block"].guardrail_id}
    GUARDRAIL_VERSION=${aws_bedrock_guardrail_version.pii["block"].version}

    # SSN is MASKED (used by `make strands-mask` / `make langgraph-mask`)
    GUARDRAIL_ID_MASK=${aws_bedrock_guardrail.pii["mask"].guardrail_id}
    GUARDRAIL_VERSION_MASK=${aws_bedrock_guardrail_version.pii["mask"].version}
  EOT
}
