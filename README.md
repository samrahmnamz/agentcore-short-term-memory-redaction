# Redact-then-store for AgentCore short-term memory

A deployable reference for the **redact-then-store** pattern: put a Bedrock
Guardrails *sensitive-information* filter **in front of** every write to
Amazon Bedrock AgentCore **short-term** memory, so raw PII (SSNs, etc.) never
lands in the immutable event log.

Implemented in **both Strands and LangGraph**, each as a **single
self-contained file** you can copy as a template, with Terraform for the
infrastructure and scripts to make it easy to test and deploy.

> **Why this matters.** AgentCore short-term memory stores raw turn-by-turn
> events via `CreateEvent`, and those events are **immutable** — once written,
> you cannot scrub them. The only safe place to redact is *upstream* of the
> write. Long-term memory strategies already filter PII, but short-term (raw
> events) does not, so compliance rules that prohibit PII in *any* stored form
> require applying a Guardrails filter before writing short-term events too.
> (AWS Well-Architected Agentic AI Lens, AGENTSEC08-BP02.)

## Policy

| Entity | Action | Effect |
| --- | --- | --- |
| `US_SOCIAL_SECURITY_NUMBER` | **BLOCK** or **ANONYMIZE** | depends which guardrail you call |
| Email, phone, address, name, DOB, cards, keys, … | **ANONYMIZE** | Masked, e.g. `My email is {EMAIL}` — turn stays usable |

**Two guardrails are deployed**, differing only in the SSN action:

- the **block** guardrail — SSN is **BLOCKED** (the turn is refused; a
  placeholder is stored). Use this when masking isn't enough for SSN.
- the **mask** guardrail — SSN is **ANONYMIZED** to
  `{US_SOCIAL_SECURITY_NUMBER}`, keeping the turn usable.

Everything else is ANONYMIZED by both. The app chooses the behavior purely by
which guardrail id it calls — there is no block/mask logic in the code:

```bash
# SSN blocked (uses the block guardrail — the default GUARDRAIL_ID)
make strands        # or: make langgraph

# SSN masked (uses the mask guardrail — GUARDRAIL_ID_MASK)
make strands-mask   # or: make langgraph-mask

# customize the text in any target:
make strands TEXT="My SSN is 123-45-6789 and email jane@example.com"
```

`terraform output` emits both ids (`block_guardrail_id`, `mask_guardrail_id`);
`make env` writes `GUARDRAIL_ID` (block) and `GUARDRAIL_ID_MASK` into `app/.env`.

## Architecture

```
 user turn  ─┐
             ├─►  sanitize(text, source)   # inline in each app file
 model turn ─┘        • apply_guardrail(guardrailId=GUARDRAIL_ID, source=…)
                      • guardrail blocked  -> store a placeholder
                      • guardrail masked   -> store the masked text ({TYPE})
                      • nothing sensitive  -> store as-is
                              │  (only sanitized text)
                              ▼
                  session.add_turns(...)  ==  CreateEvent
                              │
                              ▼
               AgentCore SHORT-TERM memory (immutable)
```

Both apps call `sanitize()` BEFORE `add_turns`, so raw PII never reaches the
immutable event log. The guardrail (not the code) decides block vs mask.

## Layout

```
.
├── app/
│   ├── strands_app.py              # Strands  — single self-contained file
│   └── langgraph_app.py            # LangGraph — single self-contained file
├── terraform/                      # two guardrails + memory + IAM
├── tests/test_sanitizer.py         # unit tests for sanitize() (no AWS needed)
├── scripts/
│   ├── setup.sh                    # venv + deps + tests
│   └── smoke_test_guardrail.py     # live check of the guardrail response
├── Makefile                        # make deploy / env / test / strands ...
└── .env.example
```

## Prerequisites

- An AWS account with Bedrock + AgentCore access in a supported region
  (default `us-west-2`).
- Enabled model access for the `MODEL_ID` you choose (default Claude Haiku 4.5).
- Terraform >= 1.5, Python >= 3.10, AWS credentials configured.

## Quick start

```bash
# 1. Local setup + unit tests (no AWS needed)
./scripts/setup.sh
source .venv/bin/activate

# 2. Provision infra (two guardrails, memory, IAM)
make deploy

# 3. Generate app/.env from terraform outputs (block + mask guardrail ids)
make env

# 4. Confirm the live guardrail response shape (recommended once)
set -a; . app/.env; set +a
python scripts/smoke_test_guardrail.py

# 5. Run either implementation (default policy: SSN blocked)
make strands        # or: make langgraph

#    ...or run with SSN masked instead of blocked:
make strands-mask   # or: make langgraph-mask

#    customize the input text on any target:
make strands TEXT="My SSN is 123-45-6789 and email jane@example.com, check my claim"
```

What you'll see, per turn: the raw text and what was actually stored in
short-term memory — with the block guardrail the SSN turn becomes a placeholder
(`[redacted: blocked sensitive data]`); with the mask guardrail it becomes
`My SSN is {US_SOCIAL_SECURITY_NUMBER} and email {EMAIL}, …`.

## The `sanitize()` function

Each app file contains the same small function — copy it into your own agent:

```python
def sanitize(text: str, source: str) -> str:
    # source = "INPUT" for user turns, "OUTPUT" for assistant turns
    resp = bedrock.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,          # block or mask guardrail
        guardrailVersion=GUARDRAIL_VERSION,
        source=source,
        content=[{"text": {"text": text}}],
    )
    if resp.get("action") != "GUARDRAIL_INTERVENED":
        return text                                 # nothing sensitive
    if "block" in resp.get("actionReason", "").lower():
        return "[redacted: blocked sensitive data]" # guardrail blocked the turn
    return resp["outputs"][0]["text"]               # guardrail's masked text
```

Call it on every turn **before** `session.add_turns(...)`. The guardrail — not
the code — decides block vs mask; the function just stores what comes back.

## Testing

```bash
make test        # unit tests with a mocked bedrock client (no AWS, no cost)
```

The tests import `sanitize()` from the Strands app with a fake bedrock client
and cover the clean / SSN-block / SSN-mask / other-PII-mask paths, asserting
raw PII never survives.

## A note on the response shape

`apply_guardrail`'s `outputs` structure can vary with your masking config.

**Verified against a live guardrail (important):** on a **BLOCK**, the API does
*not* leave `outputs` empty — it returns the *blocked-messaging* string in
`outputs[0]["text"]` and marks the offending entity with `action == "BLOCKED"`
in `assessments[].sensitiveInformationPolicy.piiEntities[]`. So the sanitizer
detects BLOCK from the per-entity action / `actionReason` (not from empty
outputs), and never mistakes the blocked-messaging for usable masked text. On
an **ANONYMIZE**, the masked text (e.g. `{EMAIL}`) is in `outputs[0]["text"]`.

Run `scripts/smoke_test_guardrail.py` once against your deployed guardrail to
confirm this shape in your account before relying on it in production.

## IAM: what the agent needs for memory to work

`ApplyGuardrail` and `InvokeModel` are covered by `AmazonBedrockFullAccess`, but
the AgentCore memory write/read APIs are **not**. Terraform emits a scoped
policy (`terraform output app_policy_arn`) granting exactly:

- `bedrock:ApplyGuardrail` (on the guardrail ARN)
- `bedrock:InvokeModel` / `InvokeModelWithResponseStream`
- `bedrock-agentcore:CreateEvent`, `ListEvents`, `GetEvent`,
  `RetrieveMemoryRecords`, `ListMemoryRecords`, `GetMemoryRecord` (on the memory ARN)
- `logs:CreateLogGroup`/`CreateLogStream`/`PutLogEvents` (audit, when enabled)

Attach it to whatever principal runs the agent:

```bash
aws iam attach-role-policy \
  --role-name <your-agent-role> \
  --policy-arn "$(cd terraform && terraform output -raw app_policy_arn)"
```

Short-term-only memory does **not** need a memory execution role (that is only
for long-term / custom strategies). This stack omits it by default via
`enable_memory_execution_role=false`.

## Teardown

```bash
make destroy
```

## Cost

`ApplyGuardrail`, AgentCore memory, and CloudWatch Logs incur AWS charges.
For current pricing see the AWS pricing pages / AWS Pricing Calculator.
