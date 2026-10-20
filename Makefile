.PHONY: help venv install install-dev test deploy destroy env plan strands strands-mask langgraph langgraph-mask fmt validate clean

TF_DIR := terraform
ENV_FILE := app/.env
PY := python3
# Default demo text (an SSN so BLOCK vs MASK is visible). Override with TEXT="...".
TEXT ?= My SSN is 123-45-6789 and email jane@example.com, check my claim

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Create a local virtualenv in .venv
	$(PY) -m venv .venv
	@echo "Activate with: source .venv/bin/activate"

install: ## Install runtime dependencies
	$(PY) -m pip install -r requirements.txt

install-dev: ## Install test/dev dependencies
	$(PY) -m pip install -r requirements-dev.txt

test: ## Run unit tests (no AWS needed)
	$(PY) -m pytest -q

plan: ## terraform plan
	cd $(TF_DIR) && terraform init -upgrade && terraform plan

deploy: ## terraform apply (creates guardrail + memory + IAM + logs)
	cd $(TF_DIR) && terraform init -upgrade && terraform apply -auto-approve

destroy: ## Tear down all infrastructure
	cd $(TF_DIR) && terraform destroy -auto-approve

env: ## Write app/.env from terraform outputs
	@cd $(TF_DIR) && terraform output -raw env_file_contents > ../$(ENV_FILE)
	@echo "Wrote $(ENV_FILE)"

fmt: ## terraform fmt
	cd $(TF_DIR) && terraform fmt -recursive

validate: ## terraform validate
	cd $(TF_DIR) && terraform init -backend=false && terraform validate

strands: ## Run Strands with the BLOCK guardrail (default). TEXT="..." to customize
	set -a; [ -f $(ENV_FILE) ] && . ./$(ENV_FILE); set +a; \
		$(PY) app/strands_app.py "$(TEXT)"

strands-mask: ## Run Strands with the MASK guardrail (SSN anonymized)
	set -a; [ -f $(ENV_FILE) ] && . ./$(ENV_FILE); set +a; \
		GUARDRAIL_ID=$$GUARDRAIL_ID_MASK GUARDRAIL_VERSION=$$GUARDRAIL_VERSION_MASK \
		$(PY) app/strands_app.py "$(TEXT)"

langgraph: ## Run LangGraph with the BLOCK guardrail (default). TEXT="..." to customize
	set -a; [ -f $(ENV_FILE) ] && . ./$(ENV_FILE); set +a; \
		$(PY) app/langgraph_app.py "$(TEXT)"

langgraph-mask: ## Run LangGraph with the MASK guardrail (SSN anonymized)
	set -a; [ -f $(ENV_FILE) ] && . ./$(ENV_FILE); set +a; \
		GUARDRAIL_ID=$$GUARDRAIL_ID_MASK GUARDRAIL_VERSION=$$GUARDRAIL_VERSION_MASK \
		$(PY) app/langgraph_app.py "$(TEXT)"

clean: ## Remove caches and venv
	rm -rf .venv .pytest_cache **/__pycache__ */__pycache__
