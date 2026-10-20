"""
LangGraph redact-then-store — single-file template.

Graph: agent -> store. The store node sanitizes each turn through a Bedrock
Guardrail BEFORE writing it to AgentCore short-term memory. Short-term events
are immutable, so this is the only safe place to remove PII.

Policy:
    SSN        -> BLOCK      (don't store the raw turn; store a placeholder)
    other PII  -> ANONYMIZE  (mask to {EMAIL}, {PHONE}, ... and keep the turn)
Flip SSN to masking with SSN_ACTION=ANONYMIZE (no redeploy).

Run:
    python app/langgraph_app.py "My SSN is 123-45-6789, check my claim"
"""

import os
import sys
import uuid
from typing import TypedDict

import boto3
from langgraph.graph import StateGraph, START, END
from langchain_aws import ChatBedrockConverse
from bedrock_agentcore.memory import MemorySessionManager
from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

REGION = os.environ.get("AWS_REGION", "us-west-2")
MEMORY_ID = os.environ["MEMORY_ID"]
GUARDRAIL_ID = os.environ["GUARDRAIL_ID"]
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")
SSN_ACTION = os.environ.get("SSN_ACTION", "BLOCK").upper()  # BLOCK | ANONYMIZE
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
llm = ChatBedrockConverse(model=MODEL_ID, region_name=REGION)
manager = MemorySessionManager(memory_id=MEMORY_ID, region_name=REGION)


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

    entities = []
    for a in resp.get("assessments", []):
        for pii in a.get("sensitiveInformationPolicy", {}).get("piiEntities", []):
            entities.append({"type": pii["type"], "match": pii.get("match", "")})

    if SSN_ACTION == "BLOCK" and any(e["type"] == "US_SOCIAL_SECURITY_NUMBER" for e in entities):
        return "[redacted: blocked sensitive data]"

    for e in entities:
        if e["match"]:
            text = text.replace(e["match"], "{%s}" % e["type"])
    return text


# ---------------------------------- graph ---------------------------------- #
class State(TypedDict):
    user_input: str
    assistant_output: str
    session_id: str


def agent(state: State) -> State:
    reply = llm.invoke([("system", "You are a helpful claims assistant."),
                        ("human", state["user_input"])])
    state["assistant_output"] = reply.content
    return state


def store(state: State) -> State:
    session = manager.create_memory_session(actor_id="user-123", session_id=state["session_id"])
    # Sanitize BEFORE add_turns (CreateEvent) — never after.
    session.add_turns(messages=[ConversationalMessage(sanitize(state["user_input"], "INPUT"), MessageRole.USER)])
    session.add_turns(messages=[ConversationalMessage(sanitize(state["assistant_output"], "OUTPUT"), MessageRole.ASSISTANT)])
    return state


def build_graph():
    g = StateGraph(State)
    g.add_node("agent", agent)
    g.add_node("store", store)
    g.add_edge(START, "agent")
    g.add_edge("agent", "store")
    g.add_edge("store", END)
    return g.compile()


def main() -> None:
    user_text = sys.argv[1] if len(sys.argv) > 1 else "My SSN is 123-45-6789, check my claim"
    build_graph().invoke({
        "user_input": user_text,
        "assistant_output": "",
        "session_id": f"langgraph-{uuid.uuid4().hex[:8]}",
    })
    print("stored sanitized turns to short-term memory.")


if __name__ == "__main__":
    main()
