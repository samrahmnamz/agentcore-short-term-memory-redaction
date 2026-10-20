"""
Strands redact-then-store — single-file template.

Sanitize every turn through a Bedrock Guardrail BEFORE writing it to AgentCore
short-term memory. Short-term events are immutable, so this is the only safe
place to remove PII.

Policy:
    SSN        -> BLOCK      (don't store the raw turn; store a placeholder)
    other PII  -> ANONYMIZE  (mask to {EMAIL}, {PHONE}, ... and keep the turn)
Flip SSN to masking with SSN_ACTION=ANONYMIZE (no redeploy).

Run:
    python app/strands_app.py "My SSN is 123-45-6789, check my claim"
"""

import os
import sys
import uuid

import boto3
from strands import Agent
from bedrock_agentcore.memory import MemorySessionManager
from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

REGION = os.environ.get("AWS_REGION", "us-west-2")
MEMORY_ID = os.environ["MEMORY_ID"]
GUARDRAIL_ID = os.environ["GUARDRAIL_ID"]
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")
SSN_ACTION = os.environ.get("SSN_ACTION", "BLOCK").upper()  # BLOCK | ANONYMIZE
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)


# ---------------------------- redact-then-store ---------------------------- #
def sanitize(text: str, source: str) -> str:
    """
    Return text safe to store. source is "INPUT" (user) or "OUTPUT" (assistant).
    Returns a placeholder string if the turn must be blocked (e.g. an SSN).
    """
    if not text.strip():
        return text

    resp = bedrock.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source=source,
        content=[{"text": {"text": text}}],
    )
    if resp.get("action") != "GUARDRAIL_INTERVENED":
        return text  # nothing sensitive

    # Collect every PII entity the guardrail detected.
    entities = []
    for a in resp.get("assessments", []):
        for pii in a.get("sensitiveInformationPolicy", {}).get("piiEntities", []):
            entities.append({"type": pii["type"], "match": pii.get("match", "")})

    # SSN + BLOCK policy -> refuse to store the raw turn.
    if SSN_ACTION == "BLOCK" and any(e["type"] == "US_SOCIAL_SECURITY_NUMBER" for e in entities):
        return "[redacted: blocked sensitive data]"

    # Otherwise mask each value to {TYPE} and keep the turn usable.
    for e in entities:
        if e["match"]:
            text = text.replace(e["match"], "{%s}" % e["type"])
    return text


# --------------------------------- agent ---------------------------------- #
def main() -> None:
    user_text = sys.argv[1] if len(sys.argv) > 1 else "My SSN is 123-45-6789, check my claim"

    agent = Agent(model=MODEL_ID, system_prompt="You are a helpful claims assistant.")
    assistant_text = str(agent(user_text))

    manager = MemorySessionManager(memory_id=MEMORY_ID, region_name=REGION)
    session = manager.create_memory_session(
        actor_id="user-123", session_id=f"strands-{uuid.uuid4().hex[:8]}"
    )

    # Sanitize BEFORE add_turns (CreateEvent) — never after.
    session.add_turns(messages=[ConversationalMessage(sanitize(user_text, "INPUT"), MessageRole.USER)])
    session.add_turns(messages=[ConversationalMessage(sanitize(assistant_text, "OUTPUT"), MessageRole.ASSISTANT)])

    print("stored in short-term memory:")
    for turn in session.get_last_k_turns(k=2):
        print(" ", turn)


if __name__ == "__main__":
    main()
