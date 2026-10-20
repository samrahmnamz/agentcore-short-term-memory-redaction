"""
Unit tests for the inline sanitize() in app/strands_app.py.

No AWS access needed: we set the required env vars before import, then swap the
module's bedrock client for a fake that returns canned apply_guardrail
responses. (strands_app.py and langgraph_app.py share the same sanitize().)

The guardrail owns the block-vs-mask decision, so these tests feed the three
real response shapes and assert sanitize() stores the right thing:
    • no PII       -> original text
    • blocked      -> placeholder (never the raw text or blocked-messaging)
    • anonymized   -> the guardrail's masked text

Run:  pytest -q
"""

import importlib
import os
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
sys.path.insert(0, APP_DIR)

os.environ.setdefault("GUARDRAIL_ID", "gr-test")
os.environ.setdefault("MEMORY_ID", "mem-test")
os.environ.setdefault("AWS_REGION", "us-west-2")


class FakeBedrock:
    def __init__(self, response):
        self.response = response
        self.last_call = None

    def apply_guardrail(self, **kwargs):
        self.last_call = kwargs
        return self.response


def load_app(response):
    if "strands_app" in sys.modules:
        del sys.modules["strands_app"]
    app = importlib.import_module("strands_app")
    app.bedrock = FakeBedrock(response)
    return app


NO_PII = {"action": "NONE"}

# Real BLOCK shape: actionReason says blocked; outputs holds blocked-messaging.
SSN_BLOCK = {
    "action": "GUARDRAIL_INTERVENED",
    "actionReason": "Guardrail blocked.",
    "outputs": [{"text": "This input was blocked ..."}],
}

# Real ANONYMIZE shape: masked text in outputs[0].text.
EMAIL_MASK = {
    "action": "GUARDRAIL_INTERVENED",
    "actionReason": "Guardrail anonymized.",
    "outputs": [{"text": "Email {EMAIL} or call {PHONE}"}],
}

SSN_MASK = {
    "action": "GUARDRAIL_INTERVENED",
    "actionReason": "Guardrail anonymized.",
    "outputs": [{"text": "My SSN is {US_SOCIAL_SECURITY_NUMBER}"}],
}


def test_clean_text_passes_through():
    app = load_app(NO_PII)
    assert app.sanitize("hello, nothing sensitive", "INPUT") == "hello, nothing sensitive"


def test_block_stores_placeholder_not_raw():
    app = load_app(SSN_BLOCK)
    out = app.sanitize("My SSN is 123-45-6789", "INPUT")
    assert out == "[redacted: blocked sensitive data]"
    assert "123-45-6789" not in out
    assert "blocked ..." not in out  # never store the blocked-messaging either


def test_other_pii_is_masked():
    app = load_app(EMAIL_MASK)
    out = app.sanitize("Email jane@x.com or call 415-555-0199", "INPUT")
    assert out == "Email {EMAIL} or call {PHONE}"


def test_mask_guardrail_masks_ssn():
    app = load_app(SSN_MASK)
    out = app.sanitize("My SSN is 123-45-6789", "INPUT")
    assert out == "My SSN is {US_SOCIAL_SECURITY_NUMBER}"
    assert "123-45-6789" not in out


def test_source_is_passed_through():
    app = load_app(NO_PII)
    app.sanitize("hi", "OUTPUT")
    assert app.bedrock.last_call["source"] == "OUTPUT"


def test_empty_text_skips_guardrail():
    app = load_app(NO_PII)
    assert app.sanitize("   ", "INPUT") == "   "
    assert app.bedrock.last_call is None
