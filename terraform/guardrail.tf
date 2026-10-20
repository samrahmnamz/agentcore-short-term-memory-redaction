#############################################
# Bedrock Guardrail: SSN=BLOCK, other PII=ANONYMIZE
#############################################

# Full set of PII entities to ANONYMIZE (everything except SSN, which gets its
# own stricter action). This is the "mask most PII" half of the policy.
locals {
  anonymized_pii_entities = [
    "ADDRESS",
    "AGE",
    "DRIVER_ID",
    "EMAIL",
    "LICENSE_PLATE",
    "NAME",
    "PASSWORD",
    "PHONE",
    "USERNAME",
    "VEHICLE_IDENTIFICATION_NUMBER",
    "CA_HEALTH_NUMBER",
    "CA_SOCIAL_INSURANCE_NUMBER",
    "US_BANK_ACCOUNT_NUMBER",
    "US_BANK_ROUTING_NUMBER",
    "US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER",
    "US_PASSPORT_NUMBER",
    "CREDIT_DEBIT_CARD_NUMBER",
    "CREDIT_DEBIT_CARD_CVV",
    "CREDIT_DEBIT_CARD_EXPIRY",
    "PIN",
    "IP_ADDRESS",
    "MAC_ADDRESS",
    "URL",
    "AWS_ACCESS_KEY",
    "AWS_SECRET_KEY",
  ]
}

resource "aws_bedrock_guardrail" "pii" {
  name                      = "${var.name_prefix}-guardrail"
  description               = "Redact-then-store filter: SSN=${var.ssn_action}, other PII=${var.other_pii_action}."
  blocked_input_messaging   = "This input was blocked because it contained sensitive information that cannot be stored."
  blocked_outputs_messaging = "This response was blocked because it contained sensitive information that cannot be stored."

  sensitive_information_policy_config {
    # SSN: its own action (BLOCK by default) applied to both input and output.
    pii_entities_config {
      type           = "US_SOCIAL_SECURITY_NUMBER"
      action         = var.ssn_action
      input_action   = var.ssn_action
      output_action  = var.ssn_action
      input_enabled  = true
      output_enabled = true
    }

    # All other PII entities: ANONYMIZE (mask) by default.
    dynamic "pii_entities_config" {
      for_each = toset(local.anonymized_pii_entities)
      content {
        type           = pii_entities_config.value
        action         = var.other_pii_action
        input_action   = var.other_pii_action
        output_action  = var.other_pii_action
        input_enabled  = true
        output_enabled = true
      }
    }

    # Belt-and-suspenders: a regex that catches SSN formatting even if the
    # managed entity detector misses an edge case. Mirrors ssn_action.
    regexes_config {
      name           = "ssn_pattern"
      description    = "Catches NNN-NN-NNNN / NNN NN NNNN SSN formats."
      pattern        = "\\b\\d{3}[- ]?\\d{2}[- ]?\\d{4}\\b"
      action         = var.ssn_action
      input_action   = var.ssn_action
      output_action  = var.ssn_action
      input_enabled  = true
      output_enabled = true
    }
  }

  tags = var.tags
}

# A published version so callers can pin GUARDRAIL_VERSION to a stable number
# instead of DRAFT. Comment this out to use "DRAFT" during development.
resource "aws_bedrock_guardrail_version" "pii" {
  guardrail_arn = aws_bedrock_guardrail.pii.guardrail_arn
  description   = "Initial published version for redact-then-store."
}
