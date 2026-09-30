# SupplyChainOps - end-to-end pipeline entry points.
# Local dev and CI use DuckDB; set DBT_TARGET=prod / WAREHOUSE_BACKEND=bigquery for BigQuery.

PY ?= python
DBT ?= dbt
DBT_ARGS := --project-dir dbt --profiles-dir dbt
export DBT_SEND_ANONYMOUS_USAGE_STATS=false
export DUCKDB_PATH ?= data/warehouse/supplychainops.duckdb

.PHONY: help venv data load dbt-build dbt-test dbt-docs forecast dashboard pipeline test lint api slack docker-build docker-up clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Create .venv and install requirements
	python3 -m venv .venv && . .venv/bin/activate && pip install -q --upgrade pip && pip install -q -r requirements.txt

data: ## Download the Olist CSVs (Kaggle CLI if configured, else public mirror)
	$(PY) -m ingestion.load_olist download

load: data ## Load raw CSVs into the warehouse (WAREHOUSE_BACKEND=duckdb|bigquery)
	$(PY) -m ingestion.load_olist load

dbt-build: ## Build + test all dbt models except the forecast marts
	$(DBT) build $(DBT_ARGS) --exclude tag:forecast

dbt-build-forecast: ## Build the forecast-dependent marts (run after `make forecast`)
	$(DBT) build $(DBT_ARGS) --select tag:forecast

dbt-test: ## Run dbt tests only
	$(DBT) test $(DBT_ARGS)

dbt-docs: ## Generate dbt docs (manifest + catalog used by the assistant)
	$(DBT) docs generate $(DBT_ARGS)

forecast: ## Train, backtest and write demand + delivery-time forecasts
	$(PY) -m forecasting.run

dashboard: ## Render the KPI dashboard to dashboard/output/kpi_dashboard.html (local check)
	$(PY) -m dashboard.render

pipeline: load dbt-build forecast dbt-build-forecast dbt-docs dashboard ## Full end-to-end run

test: ## Unit tests
	$(PY) -m pytest

lint: ## Ruff lint + format check
	ruff check . && ruff format --check .

api: ## Run the assistant API locally
	uvicorn assistant.app.main:app --host 0.0.0.0 --port 8000 --reload

slack: ## Run the Slack bot (Socket Mode)
	$(PY) -m assistant.app.slack_bot

docker-build: ## Build the assistant image
	docker build -t supplychainops-assistant -f assistant/Dockerfile .

docker-up: ## Start API + Slack bot with docker compose
	docker compose -f assistant/docker-compose.yml up --build

clean: ## Remove build artefacts (keeps downloaded data)
	rm -rf dbt/target dbt/logs dashboard/output .pytest_cache .ruff_cache
