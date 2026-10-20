terraform {
  required_version = ">= 1.5.0"

  required_providers {
    # Native AWS provider: Bedrock Guardrail, IAM, CloudWatch Logs.
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60.0"
    }
    # Cloud Control provider: AgentCore Memory is not yet in the native aws
    # provider, but AWS::BedrockAgentCore::Memory is available via awscc.
    awscc = {
      source  = "hashicorp/awscc"
      version = ">= 1.0.0"
    }
  }
}

provider "aws" {
  region = var.region
}

provider "awscc" {
  region = var.region
}
