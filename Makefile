# LLM Pre-Send Leakage Benchmark — common dev tasks.
# Source of truth for local dev workflow. Mirrored by .github/workflows/ci.yml.
#
# Use `make help` to list available targets.

.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

UV ?= uv

.PHONY: help install dev-install hooks lint format format-check type-check security secret-scan test test-cov ci-precheck clean

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
	$(UV) run bandit -r corpus harness -ll -c pyproject.toml

secret-scan:  ## Run gitleaks against the working tree + history.
	@command -v gitleaks >/dev/null 2>&1 || { \
		echo "gitleaks not installed. Install: brew install gitleaks"; exit 1; }
	gitleaks detect --config .gitleaks.toml --no-banner --verbose

test:  ## Run pytest.
	$(UV) run pytest

test-cov:  ## Run pytest with coverage report (also writes htmlcov/).
	$(UV) run pytest --cov --cov-report=term-missing --cov-report=html --cov-report=xml

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
