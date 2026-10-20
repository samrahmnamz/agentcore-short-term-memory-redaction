"""
Unit tests for the inline sanitize() in app/strands_app.py.

No AWS access needed: we set the required env vars before import, then swap the
module's bedrock client for a fake that returns canned apply_guardrail
responses. (strands_app.py and langgraph_app.py share the same sanitize().)

Run:  pytest -q
"""

import importlib
import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
sys.path.insert(0, APP_DIR)

# Env the app reads at import time.
os.environ.setdefault("GUARDRAIL_ID", "gr-test")
os.environ.setdefault("MEMORY_ID", "mem-test")
os.environ.setdefault("AWS_REGION", "us-west-2")


class FakeBedrock:
    """Returns a canned apply_guardrail response and records the last call."""

    def __init__(self, response):
        self.response = response
        self.last_call = None

    def apply_guardrail(self, **kwargs):
        self.last_call = kwargs
        return self.response


def load_app(response, ssn_action="BLOCK"):
    """Import strands_app fresh with a given SSN policy and a fake bedrock client."""
    os.environ["SSN_ACTION"] = ssn_action
    # Avoid building a real MemorySessionManager/boto client at import time by
    # importing only after stubbing is not possible here, so we import then
    # replace the module-level bedrock client the sanitize() function uses.
    if "strands_app" in sys.modules:
        del sys.modules["strands_app"]
    app = importlib.import_module("strands_app")
    app.bedrock = FakeBedrock(response)
    app.SSN_ACTION = ssn_action
    return app


# Realistic BLOCK response for an SSN (verified against a live guardrail):
# outputs holds blocked-messaging; the entity is marked action == "BLOCKED".
SSN_BLOCK = {
    "action": "GUARDRAIL_INTERVENED",
    "actionReason": "Guardrail blocked.",
    "outputs": [{"text": "This input was blocked ..."}],
    "assessments": [
        {"sensitiveInformationPolicy": {"piiEntities": [
            {"type": "US_SOCIAL_SECURITY_NUMBER", "action": "BLOCKED", "match": "123-45-6789"}
        ]}}
    ],
}

EMAIL_PHONE_ANON = {
    "action": "GUARDRAIL_INTERVENED",
    "outputs": [{"text": "ignored by client-side masking"}],
    "assessments": [
        {"sensitiveInformationPolicy": {"piiEntities": [
            {"type": "EMAIL", "action": "ANONYMIZED", "match": "jane@x.com"},
            {"type": "PHONE", "action": "ANONYMIZED", "match": "415-555-0199"},
        ]}}
    ],
}

NO_PII = {"action": "NONE"}


def test_clean_text_passes_through():
    app = load_app(NO_PII)
    assert app.sanitize("hello, nothing sensitive", "INPUT") == "hello, nothing sensitive"


def test_ssn_blocked_by_default():
    app = load_app(SSN_BLOCK, ssn_action="BLOCK")
    out = app.sanitize("My SSN is 123-45-6789", "INPUT")
    assert out == "[redacted: blocked sensitive data]"
    assert "123-45-6789" not in out


def test_ssn_masked_when_flipped_to_anonymize():
    app = load_app(SSN_BLOCK, ssn_action="ANONYMIZE")
    out = app.sanitize("My SSN is 123-45-6789", "INPUT")
    assert out == "My SSN is {US_SOCIAL_SECURITY_NUMBER}"
    assert "123-45-6789" not in out


def test_other_pii_is_masked():
    app = load_app(EMAIL_PHONE_ANON)
    out = app.sanitize("Email jane@x.com or call 415-555-0199", "INPUT")
    assert out == "Email {EMAIL} or call {PHONE}"
    assert "jane@x.com" not in out and "415-555-0199" not in out


def test_source_is_passed_through():
    app = load_app(NO_PII)
    app.sanitize("hi", "OUTPUT")
    assert app.bedrock.last_call["source"] == "OUTPUT"


def test_empty_text_skips_guardrail():
    app = load_app(NO_PII)
    assert app.sanitize("   ", "INPUT") == "   "
    assert app.bedrock.last_call is None
