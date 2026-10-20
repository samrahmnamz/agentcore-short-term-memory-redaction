"""
Strands redact-then-store — single-file template.

Sanitize every turn through a Bedrock Guardrail BEFORE writing it to AgentCore
short-term memory. Short-term events are immutable, so this is the only safe
place to remove PII.

The guardrail itself owns the policy. Point GUARDRAIL_ID at whichever you want:
    • the BLOCK guardrail  -> SSN turns are refused (a placeholder is stored)
    • the MASK  guardrail  -> SSN is masked to {US_SOCIAL_SECURITY_NUMBER}
Other PII is masked by both. (See terraform/ for the two guardrails.)

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
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)


# ---------------------------- redact-then-store ---------------------------- #
def sanitize(text: str, source: str) -> str:
    """
    Return text safe to store. source is "INPUT" (user) or "OUTPUT" (assistant).

    The guardrail decides block vs mask:
      • nothing sensitive  -> return the text unchanged
      • guardrail blocked  -> return a placeholder (don't store the raw turn)
      • guardrail masked   -> return the masked text (e.g. "{EMAIL}")
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

    # Otherwise the guardrail masked the values; store its anonymized text.
    return resp["outputs"][0]["text"]


# --------------------------------- agent ---------------------------------- #
def main() -> None:
    user_text = sys.argv[1] if len(sys.argv) > 1 else "My SSN is 123-45-6789, check my claim"

    agent = Agent(
        model=MODEL_ID,
        system_prompt="You are a helpful claims assistant.",
        callback_handler=None,  # don't stream the reply to stdout
    )
    assistant_text = str(agent(user_text))

    manager = MemorySessionManager(memory_id=MEMORY_ID, region_name=REGION)
    session = manager.create_memory_session(
        actor_id="user-123", session_id=f"strands-{uuid.uuid4().hex[:8]}"
    )

    # Sanitize BEFORE add_turns (CreateEvent) — never after. Print raw vs stored.
    for raw, source, role in [
        (user_text, "INPUT", MessageRole.USER),
        (assistant_text, "OUTPUT", MessageRole.ASSISTANT),
    ]:
        safe = sanitize(raw, source)
        session.add_turns(messages=[ConversationalMessage(safe, role)])
        print(f"\n{role.value} raw   : {raw}")
        print(f"{role.value} stored: {safe}")


if __name__ == "__main__":
    main()
