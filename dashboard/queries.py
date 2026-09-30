"""SQL behind each dashboard block. The same queries back the Looker Studio / Power BI
pages (see dashboard/README.md); ratio KPIs are always re-aggregated from their numerator
and denominator columns rather than averaged."""

HEADLINE = """
select
    sum(orders)                                             as orders,
    sum(delivered_orders)                                   as delivered_orders,
    sum(on_time_orders) * 1.0 / nullif(sum(delivered_orders), 0) as on_time_rate,
    sum(contribution_margin) / nullif(sum(orders), 0)       as margin_per_order,
    sum(delivery_cost) / nullif(sum(delivered_orders), 0)   as cost_per_delivery,
    sum(gmv)                                                as gmv,
    sum(delivery_cost)                                      as delivery_cost,
    sum(contribution_margin)                                as contribution_margin
from {schema}.mart_kpi_daily_region
where date_day between '{start}' and '{end}'
"""

WEEKLY_SERVICE_BY_REGION = """
select
    week_start,
    macro_region,
    sum(delivered_orders)                                       as delivered_orders,
    sum(on_time_orders) * 1.0 / nullif(sum(delivered_orders), 0) as on_time_rate,
    sum(avg_delivery_days * delivered_orders) / nullif(sum(delivered_orders), 0) as avg_delivery_days
from {schema}.mart_kpi_daily_region as k
join {schema}.dim_dates as d on k.date_day = d.date_day
where k.date_day between '{start}' and '{end}'
group by 1, 2
order by 1, 2
"""

MONTHLY_UNIT_ECONOMICS = """
select
    month_start,
    sum(orders)                                             as orders,
    sum(contribution_margin) / nullif(sum(orders), 0)       as margin_per_order,
    sum(delivery_cost) / nullif(sum(delivered_orders), 0)   as cost_per_delivery,
    sum(platform_revenue) / nullif(sum(orders), 0)          as revenue_per_order,
    sum(platform_cost) / nullif(sum(orders), 0)             as cost_per_order,
    sum(gmv) / nullif(sum(orders), 0)                       as avg_order_value
from {schema}.mart_unit_economics_monthly
where month_start between '{start}' and '{end}'
group by 1
order by 1
"""

STATE_SCORECARD = """
select
    state_code,
    macro_region,
    sum(orders)                                             as orders,
    sum(on_time_orders) * 1.0 / nullif(sum(delivered_orders), 0) as on_time_rate,
    sum(avg_delivery_days * delivered_orders) / nullif(sum(delivered_orders), 0) as avg_delivery_days,
    sum(contribution_margin) / nullif(sum(orders), 0)       as margin_per_order,
    sum(delivery_cost) / nullif(sum(delivered_orders), 0)   as cost_per_delivery,
    sum(gmv) / nullif(sum(orders), 0)                       as avg_order_value
from {schema}.mart_kpi_daily_region
where date_day between '{start}' and '{end}'
group by 1, 2
order by 3 desc
"""

DEMAND_ACTUAL_VS_FORECAST = """
with actual as (
    select week_start, sum(orders) as orders
    from {schema}.mart_demand_weekly_region
    group by 1
),
fc as (
    select cast(week_start as date) as week_start, forecast, forecast_lower, forecast_upper, model_name
    from {forecast_schema}.forecast_demand_weekly_region
    where region_level = 'country'
      and run_id = (select run_id from {forecast_schema}.forecast_runs where series = 'demand_orders' order by run_at desc limit 1)
)
select coalesce(a.week_start, fc.week_start) as week_start,
       a.orders, fc.forecast, fc.forecast_lower, fc.forecast_upper, fc.model_name
from actual as a
full outer join fc on a.week_start = fc.week_start
where coalesce(a.week_start, fc.week_start) >= '{start}'
order by 1
"""

FORECAST_ACCURACY_BY_REGION = """
select region_code, model_name, wape, smape, bias
from {schema}.mart_forecast_accuracy_latest
where series = '{series}' and region_level = 'macro_region' and is_champion and horizon_weeks = 0
order by wape
"""
