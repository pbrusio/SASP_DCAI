# SASP — Secure AI Security Platform
# Build and test targets

.PHONY: test-unit test-integration test-adversarial test-all lint typecheck compile-check validate-configs clean help

PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest
RUFF   ?= $(PYTHON) -m ruff

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test-unit:  ## Run unit tests only
	$(PYTEST) sasp/tests/unit/ -v --tb=short

test-integration:  ## Run integration tests (mocked services)
	$(PYTEST) sasp/tests/integration/ -v --tb=short \
		-m "not requires_kafka and not requires_triton and not requires_llm"

test-integration-full:  ## Run integration tests including live service tests
	$(PYTEST) sasp/tests/integration/ -v --tb=short

test-adversarial:  ## Run adversarial security tests
	$(PYTEST) sasp/tests/adversarial/ -v --tb=short -m adversarial

test-all:  ## Run all tests (excluding live service tests)
	$(PYTEST) sasp/tests/ -v --tb=short \
		-m "not requires_kafka and not requires_triton and not requires_llm"

test-all-full:  ## Run ALL tests including live service tests
	$(PYTEST) sasp/tests/ -v --tb=short

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

lint:  ## Run ruff linter
	$(RUFF) check sasp/ --fix

lint-check:  ## Run ruff linter (check only, no fix)
	$(RUFF) check sasp/

typecheck:  ## Run mypy type checker
	$(PYTHON) -m mypy sasp/ --ignore-missing-imports

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

compile-check:  ## Verify all Python files compile
	@echo "Checking Python compilation..."
	@find sasp/ -name "*.py" -exec $(PYTHON) -c \
		"import py_compile, sys; py_compile.compile(sys.argv[1], doraise=True)" {} \;
	@echo "All Python files compile OK"

validate-configs:  ## Validate XML and YAML config files
	@echo "Validating Splunk dashboard XMLs..."
	@for f in sasp/ui/splunk_dashboards/*.xml; do \
		$(PYTHON) -c "import xml.etree.ElementTree as ET; ET.parse('$$f')" && \
		echo "  $$f OK"; \
	done
	@echo "Validating Morpheus pipeline YAMLs..."
	@for f in sasp/models/inference/morpheus_pipelines/*.yaml; do \
		$(PYTHON) -c "\
import sys; \
content = open('$$f').read(); \
assert 'pipeline:' in content, 'Missing pipeline key'; \
print('  $$f OK')" ; \
	done
	@echo "All configs valid"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

clean:  ## Remove Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
