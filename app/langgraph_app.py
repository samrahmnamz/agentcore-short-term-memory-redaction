"""
LangGraph redact-then-store — single-file template.

Graph: agent -> store. The store node sanitizes each turn through a Bedrock
Guardrail BEFORE writing it to AgentCore short-term memory. Short-term events
are immutable, so this is the only safe place to remove PII.

The guardrail itself owns the policy. Point GUARDRAIL_ID at whichever you want:
    • the BLOCK guardrail  -> SSN turns are refused (a placeholder is stored)
    • the MASK  guardrail  -> SSN is masked to {US_SOCIAL_SECURITY_NUMBER}
Other PII is masked by both. (See terraform/ for the two guardrails.)

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
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
llm = ChatBedrockConverse(model=MODEL_ID, region_name=REGION)
manager = MemorySessionManager(memory_id=MEMORY_ID, region_name=REGION)


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
    # Sanitize BEFORE add_turns (CreateEvent) — never after. Print raw vs stored.
    for raw, source, role in [
        (state["user_input"], "INPUT", MessageRole.USER),
        (state["assistant_output"], "OUTPUT", MessageRole.ASSISTANT),
    ]:
        safe = sanitize(raw, source)
        session.add_turns(messages=[ConversationalMessage(safe, role)])
        print(f"\n{role.value} raw   : {raw}")
        print(f"{role.value} stored: {safe}")
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


if __name__ == "__main__":
    main()
