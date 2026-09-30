# SupplyChainOps

End-to-end operations analytics on the [Olist Brazilian e-commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(99,441 orders, 2016–2018: orders, items, sellers, freight, delivery dates, reviews), with an AI
assistant that answers questions over the warehouse. Built with Claude Code — session logs are in
[`docs/claude-sessions/`](docs/claude-sessions/) and the working agreement in [`CLAUDE.md`](CLAUDE.md).

```
 Kaggle / mirror ──► ingestion ──► raw.*  ──► dbt (staging → core → marts, 116 tests) ──► analytics.*
                                                                  │
                     ┌────────────────────────────────────────────┼─────────────────────────────┐
                     ▼                                            ▼                             ▼
          forecasting/ (demand + delivery time           dashboard/ (Looker Studio,      assistant/ (FastAPI +
          by region, backtested accuracy)                Power BI, local render)          Claude tool calling,
                     │                                                                   Slack bot, Docker)
                     └──► forecasts.* (append-only, accuracy tracked per run)
```

DuckDB is the local/CI warehouse; BigQuery is production. Same dbt models, same Python, one env var.

## Quick start (local, no credentials)

```bash
make venv && . .venv/bin/activate
make pipeline          # download → load → dbt build+test → forecast → forecast marts → docs → dashboard
open dashboard/output/kpi_dashboard.html
make test && make lint
```

Assistant (needs an Anthropic API key):

```bash
cp .env.example .env   # set ANTHROPIC_API_KEY
make api               # http://localhost:8000/docs
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "What was the on-time delivery rate by macro-region in 2018?"}' | jq
```

## The three deliverables

### 1. Demand and delivery-time forecasts by region (`forecasting/`)
Weekly orders and weekly average delivery days for every state, macro-region and the national total.
Candidates: 4-week moving average, YoY seasonal naive, damped Holt, and a pooled gradient-boosting
model trained across states. Each region's champion is chosen by out-of-sample WAPE over six
rolling-origin backtests with an 8-week horizon; forecasts ship with empirical 10–90 % intervals.
Every run appends to `forecasts.forecast_accuracy` / `forecast_runs`, so accuracy is tracked over time and
exposed through `mart_forecast_accuracy_latest` and `mart_forecast_vs_actual`.

Latest local run (DuckDB, training through 2018-08-13): national demand champion `seasonal_naive_yoy`,
backtest WAPE 0.23; national delivery-time champion `holt_damped`, WAPE 0.18; median state-level
champion WAPE 0.29 (demand) and 0.25 (delivery days).

### 2. Unit economics and KPI dashboard (`dashboard/`)
Margin per order, on-time rate, cost per delivery, delivery days, AOV, freight ratio by
state / macro-region / month, plus forecast pages. Looker Studio and Power BI connect to the BigQuery
marts (`dashboard/looker_studio/README.md`, `dashboard/powerbi/`); `make dashboard` renders the same
pages locally from DuckDB. Cost lines are modelled from documented assumptions in `dbt/dbt_project.yml`
because Olist publishes no cost data.

### 3. Warehouse assistant (`assistant/`)
FastAPI service using the Claude API with tool calling (`list_tables`, `describe_table`, `run_sql`).
Claude writes SQL against the dbt marts, the service runs it through a read-only guard, and the reply
carries the number **and** the exact query that produced it. If the quoted SQL did not run in that
turn, returned no rows, or the question is not answerable from the warehouse, the service returns a
refusal with a reason instead of a guess. Exposed as a Slack bot (Socket Mode) and containerised
(`assistant/Dockerfile`, `assistant/docker-compose.yml`).

## Repository map

| Path | Contents |
|---|---|
| `ingestion/` | Olist schema, downloader (Kaggle CLI or mirror), DuckDB/BigQuery loaders |
| `dbt/` | dbt project: `staging/`, `intermediate/`, `marts/core/` (dim_*, fct_*), `marts/analytics/` (mart_*), macros, tests, seeds |
| `forecasting/` | models, backtesting, runner, tests |
| `dashboard/` | queries, palette, HTML renderer, Looker Studio + Power BI guides |
| `assistant/` | FastAPI app, Claude agent, SQL guard, warehouse adapters, Slack bot, Docker, tests |
| `docs/` | `architecture.md`, `claude-sessions/` |
| `.github/workflows/ci.yml` | full DuckDB pipeline + tests + lint + Docker build |

## Production (BigQuery)

```bash
export WAREHOUSE_BACKEND=bigquery DBT_TARGET=prod GCP_PROJECT=<project> BQ_DATASET_RAW=raw_olist RAW_SCHEMA=raw_olist
export GOOGLE_APPLICATION_CREDENTIALS=/path/sa.json BQ_AUTH_METHOD=service-account
make pipeline
```

Then point Looker Studio / Power BI at `analytics.*` and run the assistant with
`WAREHOUSE_BACKEND=bigquery`.
