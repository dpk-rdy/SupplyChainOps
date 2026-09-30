# Unit economics & KPI dashboard

The dashboard reads the dbt marts in the `analytics` dataset. It exists in three forms that
share the same queries (`dashboard/queries.py`) and KPI definitions:

| Form | Where | Purpose |
|---|---|---|
| Looker Studio | `dashboard/looker_studio/` | Production dashboard on BigQuery (`dbt --target prod`) |
| Power BI | `dashboard/powerbi/` | Same pages for Power BI users: connection file + DAX measures |
| Local HTML | `python -m dashboard.render` | Credential-free render from DuckDB, used for review and CI |

## KPI definitions

All ratios are computed from numerators and denominators at query time, never averaged
across rows (averaging daily on-time rates would weight a 3-order day like a 3,000-order day).

| KPI | Definition | Source columns |
|---|---|---|
| Orders | Non-canceled orders by purchase date | `mart_kpi_daily_region.orders` |
| On-time delivery rate | delivered on or before the estimated delivery date ÷ delivered orders | `on_time_orders / delivered_orders` |
| Avg delivery days | purchase → customer delivery, delivered orders, order-weighted | `avg_delivery_days * delivered_orders / delivered_orders` |
| Margin per order | contribution margin ÷ orders. Contribution margin = (take rate × GMV + freight collected) − (carrier cost + payment fees + handling) | `contribution_margin / orders` |
| Cost per delivery | modelled carrier cost ÷ delivered orders | `delivery_cost / delivered_orders` |
| Average order value | GMV ÷ orders | `gmv / orders` |
| Freight-to-GMV | freight collected ÷ GMV | `freight_revenue / gmv` |
| Forecast accuracy | WAPE of the champion model over rolling-origin backtests | `mart_forecast_accuracy_latest.wape` |

Cost assumptions (Olist publishes no costs) are dbt vars in `dbt/dbt_project.yml`:
`marketplace_take_rate` 20 %, `payment_processing_rate` 3 %, `delivery_cost_ratio` 100 % of
freight, `handling_cost_per_order` R$ 3 + R$ 1 per extra item. Change them there and rebuild;
every KPI recomputes.

## Pages

1. **Overview** – five stat tiles (orders, on-time rate, margin per order, cost per delivery, GMV),
   weekly on-time rate and delivery days by macro-region, state scorecard table.
2. **Unit economics** – monthly margin per order and cost per delivery (two panels, one axis each),
   revenue vs cost per order, AOV, freight-to-GMV; sliced by state / macro-region.
3. **Forecast** – weekly national orders with the 8-week forecast and 10–90 % band
   (`forecast_demand_weekly_region`, `region_level = 'country'`), champion WAPE by macro-region
   for demand and delivery time (`mart_forecast_accuracy_latest`), forecast vs actual drill-down
   (`mart_forecast_vs_actual`).

## Local render

```bash
make dashboard            # -> dashboard/output/kpi_dashboard.html (open in a browser)
python -m dashboard.render --start 2018-01-01 --end 2018-08-31
```

Colors come from a validated colorblind-safe palette (`dashboard/palette.py`); macro-regions keep
a fixed hue whatever the filter, and no chart uses a dual axis.
