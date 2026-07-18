# LLM Pre-Send Leakage Benchmark — common dev tasks.
# Source of truth for local dev workflow. Mirrored by .github/workflows/ci.yml.
#
# Use `make help` to list available targets.

.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

UV ?= uv

.PHONY: help install dev-install hooks lint format format-check type-check security secret-scan test test-cov verify-corpus ci-precheck clean harness-anthropic-dry harness-anthropic harness-openai-dry harness-openai harness-bedrock-dry harness-bedrock harness-azure-dry harness-azure harness-all-dry score score-dry replicate paper paper-html paper-clean

help:  ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime deps only.
	$(UV) sync

dev-install:  ## Install runtime + dev + every harness extra.
	$(UV) sync --all-extras --dev

hooks:  ## Install git pre-commit hooks.
	$(UV) run pre-commit install
	$(UV) run pre-commit install --hook-type pre-push

lint:  ## Run ruff lint check.
	$(UV) run ruff check .

format:  ## Auto-format code with ruff (mutates files).
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

format-check:  ## Verify formatting without changing files (CI mode).
	$(UV) run ruff format --check .

type-check:  ## Run mypy in strict mode.
	$(UV) run mypy .

security:  ## Run bandit security scan on source.
	$(UV) run bandit -r corpus harness paper -ll -c pyproject.toml

secret-scan:  ## Run gitleaks against the working tree + history.
	@command -v gitleaks >/dev/null 2>&1 || { \
		echo "gitleaks not installed. Install: brew install gitleaks"; exit 1; }
	gitleaks detect --config .gitleaks.toml --no-banner --verbose

test:  ## Run pytest.
	$(UV) run pytest

test-cov:  ## Run pytest with coverage report (also writes htmlcov/).
	$(UV) run pytest --cov --cov-report=term-missing --cov-report=html --cov-report=xml

verify-corpus:  ## Reproduce corpus_v1.jsonl from scratch and confirm byte-identical output.
	@$(UV) run python corpus/generate.py --output /tmp/_corpus_check.jsonl >/dev/null 2>&1
	@if diff -q corpus/corpus_v1.jsonl /tmp/_corpus_check.jsonl > /dev/null; then \
		echo "✓ Corpus is reproducible — byte-identical from DEFAULT_SEED=20260623"; \
		rm -f /tmp/_corpus_check.jsonl; \
	else \
		echo "✗ Corpus NOT reproducible — diff (first 20 lines):"; \
		diff corpus/corpus_v1.jsonl /tmp/_corpus_check.jsonl | head -20; \
		rm -f /tmp/_corpus_check.jsonl; \
		exit 1; \
	fi

ci-precheck:  ## Run every CI gate locally. Run BEFORE git push to catch failures.
	@echo "=== 1/5 Lint (ruff check) ==="
	@$(MAKE) -s lint
	@echo "=== 2/5 Format check (ruff format --check) ==="
	@$(MAKE) -s format-check
	@echo "=== 3/5 Type check (mypy --strict) ==="
	@$(MAKE) -s type-check
	@echo "=== 4/5 Security scan (bandit) ==="
	@$(MAKE) -s security
	@echo "=== 5/5 Tests + coverage (pytest) ==="
	@$(MAKE) -s test-cov
	@echo ""
	@echo "✓ All CI gates pass. Safe to push."

clean:  ## Remove build artifacts and caches.
	rm -rf build dist *.egg-info htmlcov coverage.xml .coverage \
		.pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} \;

harness-anthropic-dry:  ## Dry-run the Anthropic harness against the full corpus (no API calls).
	$(UV) run python -m harness.api.anthropic \
		--corpus corpus/corpus_v1.jsonl \
		--output results/raw/anthropic.dryrun.json \
		--dry-run

harness-anthropic:  ## Run the Anthropic harness live. Requires ANTHROPIC_API_KEY.
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "ANTHROPIC_API_KEY is not set. Aborting."; exit 1; \
	fi
	$(UV) run python -m harness.api.anthropic \
		--corpus corpus/corpus_v1.jsonl \
		--output results/raw/anthropic.json

harness-openai-dry:  ## Dry-run the OpenAI harness against the full corpus.
	$(UV) run python -m harness.api.openai \
		--corpus corpus/corpus_v1.jsonl \
		--output results/raw/openai.dryrun.json \
		--dry-run

harness-openai:  ## Run the OpenAI harness live. Requires OPENAI_API_KEY.
	@if [ -z "$$OPENAI_API_KEY" ]; then \
		echo "OPENAI_API_KEY is not set. Aborting."; exit 1; \
	fi
	$(UV) run python -m harness.api.openai \
		--corpus corpus/corpus_v1.jsonl \
		--output results/raw/openai.json

harness-bedrock-dry:  ## Dry-run the Bedrock harness against the full corpus.
	$(UV) run python -m harness.api.bedrock \
		--corpus corpus/corpus_v1.jsonl \
		--output results/raw/bedrock.dryrun.json \
		--dry-run

harness-bedrock:  ## Run the Bedrock harness live. Requires AWS creds + AWS_REGION.
	@if [ -z "$$AWS_REGION$$AWS_DEFAULT_REGION" ]; then \
		echo "AWS_REGION (or AWS_DEFAULT_REGION) is not set. Aborting."; exit 1; \
	fi
	$(UV) run python -m harness.api.bedrock \
		--corpus corpus/corpus_v1.jsonl \
		--output results/raw/bedrock.json

harness-azure-dry:  ## Dry-run the Azure OpenAI harness. Needs --model or AZURE_OPENAI_DEPLOYMENT.
	@DEPLOYMENT="$${AZURE_OPENAI_DEPLOYMENT:-placeholder-deployment}"; \
	$(UV) run python -m harness.api.azure_openai \
		--corpus corpus/corpus_v1.jsonl \
		--output results/raw/azure_openai.dryrun.json \
		--model "$$DEPLOYMENT" \
		--dry-run

harness-azure:  ## Run the Azure OpenAI harness live. Requires AZURE_OPENAI_* env vars.
	@for v in AZURE_OPENAI_API_KEY AZURE_OPENAI_ENDPOINT AZURE_OPENAI_DEPLOYMENT; do \
		if [ -z "$${!v}" ]; then \
			echo "$$v is not set. Aborting."; exit 1; \
		fi; \
	done
	$(UV) run python -m harness.api.azure_openai \
		--corpus corpus/corpus_v1.jsonl \
		--output results/raw/azure_openai.json

harness-all-dry:  ## Dry-run every API harness. Fast smoke test with no API cost.
	@$(MAKE) -s harness-anthropic-dry
	@$(MAKE) -s harness-openai-dry
	@$(MAKE) -s harness-bedrock-dry
	@$(MAKE) -s harness-azure-dry
	@echo "✓ All API harnesses produced dry-run output."

score:  ## Score captured results and emit results/results_v1.csv.
	$(UV) run python -m harness.score \
		--raw-dir results/raw \
		--output results/results_v1.csv

score-dry:  ## Score using dry-run captures — for scoring-pipeline smoke tests only.
	@# Temporarily rename .dryrun.json → .json so discover_captures picks them
	@# up as if they were live captures; restore afterwards. The scorer will
	@# refuse to score them because they carry dry_run=True — this target
	@# exists to verify that guard fires end-to-end.
	@set -e; \
	for f in results/raw/*.dryrun.json; do \
		[ -f "$$f" ] && mv "$$f" "$${f%.dryrun.json}.json.tmp-liverename"; \
	done; \
	trap 'for f in results/raw/*.json.tmp-liverename; do [ -f "$$f" ] && mv "$$f" "$${f%.json.tmp-liverename}.dryrun.json"; done' EXIT; \
	echo "(expected to fail — scorer must reject dry-run captures)"; \
	$(UV) run python -m harness.score --raw-dir results/raw --output /tmp/score-dry.csv || echo "✓ scorer correctly rejected dry-run captures."

replicate:  ## Run every API harness live and score. Requires all vendor credentials.
	@echo "=== 1/5 anthropic ==="
	@$(MAKE) -s harness-anthropic
	@echo "=== 2/5 openai ==="
	@$(MAKE) -s harness-openai
	@echo "=== 3/5 bedrock ==="
	@$(MAKE) -s harness-bedrock
	@echo "=== 4/5 azure_openai ==="
	@$(MAKE) -s harness-azure
	@echo "=== 5/5 score ==="
	@$(MAKE) -s score
	@echo ""
	@echo "✓ Replication complete. Scored results at results/results_v1.csv."

paper:  ## Build paper HTML + PDF from paper/paper.md. Needs pandoc + `--extra paper`.
	$(UV) run python -m paper.build

paper-html:  ## Build only the HTML (no weasyprint dependency needed).
	$(UV) run python -m paper.build --html-only

paper-clean:  ## Remove generated paper artifacts.
	rm -f paper/paper.html paper/paper.pdf
