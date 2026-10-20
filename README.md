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
| `US_SOCIAL_SECURITY_NUMBER` | **BLOCK** (default) | Refuse to store the raw turn; a placeholder is stored instead |
| Email, phone, address, name, DOB, cards, keys, … | **ANONYMIZE** | Masked, e.g. `My email is {EMAIL}` — turn stays usable |

SSN uses `BLOCK` because masking isn't enough for the strictest categories.

**The MASK-vs-BLOCK decision lives in code** (the `sanitize()` function inside
each app file), driven by the `SSN_ACTION` env var — so you can flip it and
test instantly, with no redeploy:

```bash
# default: SSN is blocked (raw turn not stored)
make strands TEXT="My SSN is 123-45-6789"

# flip SSN to masking: stored as "My SSN is {US_SOCIAL_SECURITY_NUMBER}"
SSN_ACTION=ANONYMIZE make strands TEXT="My SSN is 123-45-6789"
```

When SSN is flipped to `ANONYMIZE`, `sanitize()` masks the value client-side
(`{US_SOCIAL_SECURITY_NUMBER}`) even though the deployed guardrail still blocks
SSN at the service level — defense in depth. The Terraform `ssn_action`
variable only sets the *service-level* guardrail default; the authoritative app
decision is the `SSN_ACTION` code-level policy above.

## Architecture

```
 user turn  ─┐
             ├─►  sanitize(text, source)   # inline in each app file
 model turn ─┘        • apply_guardrail(source=INPUT|OUTPUT)
                      • SSN  -> BLOCK  (store a placeholder)
                      • PII  -> ANONYMIZE (mask to {TYPE})
                              │  (only sanitized text)
                              ▼
                  session.add_turns(...)  ==  CreateEvent
                              │
                              ▼
               AgentCore SHORT-TERM memory (immutable)
```

Both apps call `sanitize()` BEFORE `add_turns`, so raw PII never reaches the
immutable event log.

## Layout

```
.
├── app/
│   ├── strands_app.py              # Strands  — single self-contained file
│   └── langgraph_app.py            # LangGraph — single self-contained file
├── terraform/                      # guardrail + memory + IAM
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

# 2. Provision infra (guardrail, memory, IAM, audit log group)
make deploy

# 3. Generate app/.env from terraform outputs
make env

# 4. Confirm the live guardrail response shape (recommended once)
set -a; . app/.env; set +a
python scripts/smoke_test_guardrail.py

# 5. Run either implementation
make strands   TEXT="My SSN is 123-45-6789 and email jane@example.com, check my claim"
make langgraph TEXT="My SSN is 123-45-6789 and email jane@example.com, check my claim"
```

What you'll see: the raw user/assistant text, then the **sanitized** turns that
were actually written to short-term memory (SSN blocked → placeholder, email →
`{EMAIL}`), plus audit lines noting the entity *types* detected.

## The `sanitize()` function

Each app file contains the same small function — copy it into your own agent:

```python
def sanitize(text: str, source: str) -> str:
    # source = "INPUT" for user turns, "OUTPUT" for assistant turns
    resp = bedrock.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source=source,
        content=[{"text": {"text": text}}],
    )
    if resp.get("action") != "GUARDRAIL_INTERVENED":
        return text                       # nothing sensitive -> store as-is
    # ... BLOCK SSN (placeholder) or mask other PII to {TYPE} ...
```

Call it on every turn **before** `session.add_turns(...)`.

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
