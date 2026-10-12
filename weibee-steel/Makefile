# Weibee Steel bid-intelligence work sample
PY ?= python

.PHONY: help venv run test lint clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

venv: ## Create .venv and install requirements
	python3 -m venv .venv && . .venv/bin/activate && pip install -q --upgrade pip && pip install -q -r requirements.txt

run: ## Generate history, build marts, fit model, score pipeline, render output/bid_intelligence_report.html
	$(PY) -m bid_intelligence run --out output --db output/warehouse.duckdb

test: ## Unit + end-to-end tests
	$(PY) -m pytest

lint: ## Ruff lint + format check
	ruff check . && ruff format --check .

clean: ## Remove generated artefacts
	rm -rf output/warehouse.duckdb .pytest_cache .ruff_cache
