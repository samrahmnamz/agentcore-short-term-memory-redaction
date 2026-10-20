variable "region" {
  description = "AWS region to deploy into. AgentCore Memory + Guardrails must be in a supported region."
  type        = string
  default     = "us-west-2"
}

variable "name_prefix" {
  description = "Prefix for all resource names."
  type        = string
  default     = "pii-redaction"
}

variable "event_expiry_days" {
  description = "Days after which short-term memory events expire (3-365)."
  type        = number
  default     = 30

  validation {
    condition     = var.event_expiry_days >= 3 && var.event_expiry_days <= 365
    error_message = "event_expiry_days must be between 3 and 365."
  }
}

variable "enable_memory_execution_role" {
  description = "Create + attach a memory execution role. Only needed for long-term / custom strategies; short-term-only memory does NOT require it."
  type        = bool
  default     = false
}

variable "manage_audit_log_group" {
  description = "Let Terraform create the CloudWatch audit log group. Set false if the deploying principal lacks logs:CreateLogGroup (the app can still create it at runtime, or disable CloudWatch audit)."
  type        = bool
  default     = true
}

variable "audit_log_group_name" {
  description = "CloudWatch Logs group for redaction audit records."
  type        = string
  default     = "/agentcore/redaction/audit"
}

variable "audit_log_retention_days" {
  description = "Retention in days for the audit log group."
  type        = number
  default     = 90
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default = {
    Project = "agentcore-pii-redaction"
    Pattern = "redact-then-store"
  }
}
