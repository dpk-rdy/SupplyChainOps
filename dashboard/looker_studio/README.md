# Looker Studio setup

Looker Studio connects directly to the BigQuery marts. Nothing is copied; every widget runs a
BigQuery query at view time.

## 1. Data sources (one per mart)

Looker Studio → *Create* → *Data source* → **BigQuery** → *My projects* → `<GCP_PROJECT>` →
dataset `analytics` → table. Add these four sources:

| Data source | Table | Date field | Default aggregation to fix |
|---|---|---|---|
| KPI daily | `analytics.mart_kpi_daily_region` | `date_day` | all rate columns → set to *None* (use calculated fields below) |
| Unit economics monthly | `analytics.mart_unit_economics_monthly` | `month_start` | same |
| Forecast vs actual | `analytics.mart_forecast_vs_actual` | `week_start` | `forecast`, `actual` → Sum |
| Forecast accuracy | `analytics.mart_forecast_accuracy_latest` | – | `wape` → Average (one row per region/model/horizon) |

If BigQuery is queried through a service account, give it `roles/bigquery.dataViewer` on the
`analytics` dataset and `roles/bigquery.jobUser` on the project.

## 2. Calculated fields (ratios must be re-aggregated)

Create these on the **KPI daily** source (same formulas on the monthly source):

```
On-time rate        = SUM(on_time_orders) / SUM(delivered_orders)
Avg delivery days   = SUM(avg_delivery_days * delivered_orders) / SUM(delivered_orders)
Margin per order    = SUM(contribution_margin) / SUM(orders)
Cost per delivery   = SUM(delivery_cost) / SUM(delivered_orders)
Average order value = SUM(gmv) / SUM(orders)
Freight to GMV      = SUM(freight_revenue) / SUM(gmv)
Contribution margin % = SUM(contribution_margin) / SUM(platform_revenue)
```

Never drop the raw `on_time_rate` / `margin_per_order` columns into a chart with a Sum or
Average aggregation – they are per-row values.

## 3. Pages and widgets

**Page 1 – Overview**
- Date range control (default: 2017-01-01 → 2018-08-31), drop-down filters on `macro_region` and `state_code`.
- Scorecards: `SUM(orders)`, On-time rate, Margin per order, Cost per delivery, `SUM(gmv)`.
  Compare to previous period enabled.
- Time series (week): On-time rate, breakdown dimension `macro_region`, 5 series max.
- Time series (week): Avg delivery days, breakdown `macro_region`.
- Table: `state_code`, `macro_region`, `SUM(orders)`, On-time rate, Avg delivery days,
  Margin per order, Cost per delivery, Average order value; sort by orders desc; heat-map on the ratio columns.

**Page 2 – Unit economics** (source: Unit economics monthly)
- Two separate time-series charts: Margin per order; Cost per delivery. Do not combine on a dual axis.
- Stacked bar by month: `SUM(delivery_cost)`, `SUM(payment_fees)`, `SUM(handling_cost)` (cost mix).
- Bar by `state_code`: Margin per order, colour by `macro_region` (fixed colours per region, see below).
- Scorecards: Average order value, Freight to GMV, Contribution margin %.

**Page 3 – Forecast**
- Time series (source: Forecast vs actual, filter `series = demand_orders`, `region_level = country`):
  `SUM(actual)`, `SUM(forecast)`, `SUM(forecast_lower)`, `SUM(forecast_upper)`; style lower/upper as
  thin dashed lines.
- Bar (source: Forecast accuracy, filter `is_champion = true`, `horizon_weeks = 0`,
  `region_level = macro_region`): `AVG(wape)` by `region_code`, one bar chart per `series`.
- Table: `region_code`, `model_name`, `horizon_weeks`, `AVG(wape)`, `AVG(smape)`, `AVG(bias)` with a
  `series` filter, for the model-selection drill-down.

## 4. Theme

Use these fixed series colours (*Theme and layout* → *Customize* → chart colours) so a region keeps
its colour regardless of filters: Sudeste `#2a78d6`, Sul `#eb6834`, Nordeste `#1baf7a`,
Centro-Oeste `#eda100`, Norte `#e87ba4`. Surface `#fcfcfb`, text `#0b0b0b`, gridlines `#e1e0d9`.

## 5. Refresh

Data freshness: 12 hours is enough; the marts rebuild when the pipeline runs
(`make pipeline` with `DBT_TARGET=prod WAREHOUSE_BACKEND=bigquery`).
