#!/usr/bin/env python3
"""
Live smoke test against the DEPLOYED guardrail.

Prints the raw apply_guardrail response for a known-PII string so you can
confirm the response shape, then shows the detected entities per sample.

    set -a; . app/.env; set +a
    python scripts/smoke_test_guardrail.py
"""

import json
import os

import boto3

GUARDRAIL_ID = os.environ["GUARDRAIL_ID"]
VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")
REGION = os.environ.get("AWS_REGION", "us-west-2")

SAMPLES = [
    ("INPUT", "My SSN is 123-45-6789, please check my claim."),
    ("INPUT", "Email me at jane.doe@example.com or call 415-555-0199."),
    ("OUTPUT", "I have confirmed your claim. Nothing sensitive here."),
]


def main() -> None:
    rt = boto3.client("bedrock-runtime", region_name=REGION)

    print("=== RAW apply_guardrail response for a known-SSN string ===")
    raw = rt.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=VERSION,
        source="INPUT",
        content=[{"text": {"text": SAMPLES[0][1]}}],
    )
    print(json.dumps(raw, indent=2, default=str))

    print("\n=== Detected entities per sample ===")
    for source, text in SAMPLES:
        resp = rt.apply_guardrail(
            guardrailIdentifier=GUARDRAIL_ID,
            guardrailVersion=VERSION,
            source=source,
            content=[{"text": {"text": text}}],
        )
        types = []
        for a in resp.get("assessments", []):
            for pii in a.get("sensitiveInformationPolicy", {}).get("piiEntities", []):
                types.append(pii["type"])
        print(f"[{source}] action={resp.get('action')} detected={sorted(set(types))}  ::  {text}")


if __name__ == "__main__":
    main()
