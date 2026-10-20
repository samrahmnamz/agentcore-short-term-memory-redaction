#############################################
# Two Bedrock Guardrails that differ ONLY in the SSN action:
#   • "block" guardrail -> SSN = BLOCK
#   • "mask"  guardrail -> SSN = ANONYMIZE
# All other PII is ANONYMIZE in both. The app picks which one to call by
# passing its GUARDRAIL_ID — no client-side masking logic needed.
#############################################

locals {
  # The SSN action for each guardrail. The map key becomes the resource key.
  guardrail_ssn_action = {
    block = "BLOCK"
    mask  = "ANONYMIZE"
  }

  # Everything except SSN is always ANONYMIZE (masked), in both guardrails.
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
  for_each = local.guardrail_ssn_action

  name                      = "${var.name_prefix}-${each.key}"
  description               = "Redact-then-store filter: SSN=${each.value}, other PII=ANONYMIZE."
  blocked_input_messaging   = "This input was blocked because it contained sensitive information that cannot be stored."
  blocked_outputs_messaging = "This response was blocked because it contained sensitive information that cannot be stored."

  sensitive_information_policy_config {
    # SSN: BLOCK in the "block" guardrail, ANONYMIZE in the "mask" guardrail.
    pii_entities_config {
      type           = "US_SOCIAL_SECURITY_NUMBER"
      action         = each.value
      input_action   = each.value
      output_action  = each.value
      input_enabled  = true
      output_enabled = true
    }

    # All other PII entities: always ANONYMIZE.
    dynamic "pii_entities_config" {
      for_each = toset(local.anonymized_pii_entities)
      content {
        type           = pii_entities_config.value
        action         = "ANONYMIZE"
        input_action   = "ANONYMIZE"
        output_action  = "ANONYMIZE"
        input_enabled  = true
        output_enabled = true
      }
    }

    # Belt-and-suspenders SSN regex, mirroring this guardrail's SSN action.
    # Belt-and-suspenders SSN regex — only on the BLOCK guardrail. On the MASK
    # guardrail it would double-tag (managed entity + regex both match the same
    # value, producing "{US_SOCIAL_SECURITY_NUMBER}{ssn_pattern}"), so we omit it.
    dynamic "regexes_config" {
      for_each = each.key == "block" ? [1] : []
      content {
        name           = "ssn_pattern"
        description    = "Catches NNN-NN-NNNN / NNN NN NNNN SSN formats."
        pattern        = "\\b\\d{3}[- ]?\\d{2}[- ]?\\d{4}\\b"
        action         = "BLOCK"
        input_action   = "BLOCK"
        output_action  = "BLOCK"
        input_enabled  = true
        output_enabled = true
      }
    }
  }

  tags = var.tags
}

# A published version for each guardrail so callers can pin a stable number.
# The terraform_data trigger republishes the version whenever the guardrail's
# own version attribute bumps (i.e. its config changed), so pinned callers
# never read a stale version.
resource "terraform_data" "guardrail_revision" {
  for_each = aws_bedrock_guardrail.pii
  input    = each.value.version
}

resource "aws_bedrock_guardrail_version" "pii" {
  for_each = aws_bedrock_guardrail.pii

  guardrail_arn = each.value.guardrail_arn
  description   = "Published version for redact-then-store (${each.key})."

  lifecycle {
    replace_triggered_by = [terraform_data.guardrail_revision[each.key]]
  }
}
