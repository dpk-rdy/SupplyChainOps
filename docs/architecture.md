# Architecture notes

## Data model

```
raw.olist_*  (9 tables, verbatim CSV)
   │ stg_*        typed, renamed, deduplicated (reviews), geolocation collapsed to one point per zip prefix
   │ int_*        order-level roll-ups: items, payments, latest review, customer↔seller distance
   ▼
core   dim_customers  dim_sellers  dim_products  dim_regions (seed)  dim_dates
       fct_orders (grain: order)      fct_order_items (grain: line item)
   ▼
marts  mart_kpi_daily_region (date × state)         mart_unit_economics_monthly (month × state)
       mart_demand_weekly_region (week × state)     mart_delivery_time_weekly_region (week × state)
       mart_seller_performance (seller)             mart_category_monthly (month × category)
       mart_forecast_vs_actual, mart_forecast_accuracy_latest  (read forecasts.* written by the forecasting job)
```

`fct_orders` carries the service-level and economics logic once; every mart aggregates it.

### Unit economics

Olist publishes prices, freight charged to the customer and payments, but no costs. The contribution
margin is therefore modelled per order from explicit dbt vars:

| Line | Formula | Var |
|---|---|---|
| take_revenue | gmv × take rate | `marketplace_take_rate` = 0.20 |
| freight_revenue | freight charged to the customer | — |
| delivery_cost | freight × ratio paid to carriers | `delivery_cost_ratio` = 1.0 |
| payment_fee | payment value × fee | `payment_processing_rate` = 0.03 |
| handling_cost | per order + per extra item | `handling_cost_per_order` = 3, `handling_cost_per_extra_item` = 1 |
| contribution_margin | take_revenue + freight_revenue − (delivery_cost + payment_fee + handling_cost) | |

Change a var, rebuild, and every KPI recomputes; `assert_margin_components_sum` guards the identity.

### Service level

`is_on_time` = delivered date ≤ estimated delivery date (date granularity, as promised to the customer),
defined only for delivered orders. `delivery_days` is purchase → delivery in fractional days.
Known data caveats: 8 "delivered" orders have no delivery timestamp (singular test tolerates ≤ 10);
the export thins out after 2018-08-19 and orders purchased in the final weeks are delivery-censored.

## Forecasting

- Series: `demand_orders` (orders per purchase week) and `delivery_days` (order-weighted average
  delivery days per purchase week), for 27 states + 5 macro-regions + Brazil.
- Tail handling: weeks whose national volume falls below 70 % of the trailing 8-week median are
  dropped (partial export weeks); the delivery series drops one extra week for censoring.
- Candidates: `moving_average_4`, `seasonal_naive_yoy` (52-week lag scaled by recent YoY growth),
  `holt_damped` (grid-searched α/β, φ = 0.9), `pooled_gbm` (one `HistGradientBoostingRegressor` across
  states on lags 1–8, 4/8-week levels, week-of-year, state; target = deviation from the 4-week level,
  log space for counts; recursive multi-step). Very small series (< 5/week) only get the moving average.
- Selection: rolling-origin backtest, 6 origins one week apart, horizon 8; champion = lowest overall
  WAPE. Intervals = forecast + empirical 10/90 % residual quantiles per horizon.
- Outputs (append-only, keyed by `run_id`): `forecast_demand_weekly_region`,
  `forecast_delivery_time_weekly_region`, `forecast_accuracy` (every candidate × horizon, `is_champion`),
  `forecast_runs`.

Honest read of the numbers: with ~90 weekly points per state, the simple models are competitive and
the pooled GBM wins only on some series. That is what the accuracy table is for — it is the record that
lets a later run (more data, new features) prove it did better.

## Assistant

```
Slack (Socket Mode) ──► FastAPI /ask ──► WarehouseAgent
                                           │  system prompt = rules + catalog (from dbt manifest), cached
                                           │  tools: list_tables · describe_table · run_sql (strict schemas)
                                           │  run_sql → sql_guard.validate → read-only warehouse → JSON rows
                                           │  final = JSON schema {status, answer, value, sql, assumptions, refusal_reason}
                                           └─ grounding check: quoted sql ∈ executed ∧ rows > 0, else refused
```

Guard rules: single SELECT/WITH statement; allow-listed `analytics.*` / `forecasts.*` tables only;
no DDL/DML/session keywords; no file or catalog functions; results wrapped in `LIMIT max_rows+1`.
DuckDB is opened `read_only=True`; BigQuery runs with `maximum_bytes_billed` and a job timeout.
Follow-up questions work per `session_id` (Slack thread); histories are append-only and bounded.

Model settings: `claude-opus-5-5`, adaptive thinking (default), `output_config.effort=medium`,
prompt caching on the system block, server-side refusal fallbacks on the Claude API
(`CLAUDE_ENABLE_FALLBACKS=false` for Bedrock/Vertex).

## Two warehouses

All SQL is written once. `dbt/macros/cross_db.sql` resolves dialect differences by `target.type`;
the assistant's BigQuery adapter rewrites `analytics.table` to `` `project.analytics.table` `` so the
same prompt works on both. Raw schema names differ (`raw` vs `raw_olist`) and are set with
`RAW_SCHEMA` / `BQ_DATASET_RAW`.
