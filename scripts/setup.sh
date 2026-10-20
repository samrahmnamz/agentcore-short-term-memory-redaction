#!/usr/bin/env bash
# One-shot local setup: venv + dependencies + run unit tests.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Creating virtualenv (.venv)"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing dependencies"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt

echo "==> Running unit tests (no AWS required)"
python -m pytest -q

echo
echo "Setup complete. Next:"
echo "  1. cd terraform && terraform init && terraform apply"
echo "  2. make env            # writes app/.env from terraform outputs"
echo "  3. make strands        # or: make langgraph"
