{# Grain: run x series x region x target week x horizon. Joins every forecast (state,
   macro-region and national level) to the realised actual so the dashboard can show
   tracked accuracy. `actual` is null for target weeks not yet observed. #}
with forecasts as (
    select run_id, run_at, series, region_level, region_code, model_name, origin_week, week_start, horizon_weeks,
           forecast, forecast_lower, forecast_upper, backtest_wape
    from {{ source('forecasts', 'forecast_demand_weekly_region') }}
    union all
    select run_id, run_at, series, region_level, region_code, model_name, origin_week, week_start, horizon_weeks,
           forecast, forecast_lower, forecast_upper, backtest_wape
    from {{ source('forecasts', 'forecast_delivery_time_weekly_region') }}
),

demand as (
    select 'state' as region_level, state_code as region_code, week_start, cast(orders as {{ dbt.type_float() }}) as actual
    from {{ ref('mart_demand_weekly_region') }}
    union all
    select 'macro_region', macro_region, week_start, cast(sum(orders) as {{ dbt.type_float() }})
    from {{ ref('mart_demand_weekly_region') }} group by 1, 2, 3
    union all
    select 'country', 'BR', week_start, cast(sum(orders) as {{ dbt.type_float() }})
    from {{ ref('mart_demand_weekly_region') }} group by 1, 2, 3
),

delivery as (
    select 'state' as region_level, state_code as region_code, week_start, avg_delivery_days as actual
    from {{ ref('mart_delivery_time_weekly_region') }}
    union all
    select 'macro_region', macro_region, week_start,
           {{ safe_divide('sum(avg_delivery_days * delivered_orders)', 'sum(delivered_orders)') }}
    from {{ ref('mart_delivery_time_weekly_region') }} group by 1, 2, 3
    union all
    select 'country', 'BR', week_start,
           {{ safe_divide('sum(avg_delivery_days * delivered_orders)', 'sum(delivered_orders)') }}
    from {{ ref('mart_delivery_time_weekly_region') }} group by 1, 2, 3
),

actuals as (
    select 'demand_orders' as series, * from demand
    union all
    select 'delivery_days' as series, * from delivery
)

select
    f.run_id,
    f.run_at,
    f.series,
    f.region_level,
    f.region_code,
    f.model_name,
    f.origin_week,
    {{ to_date('f.week_start') }}       as week_start,
    f.horizon_weeks,
    f.forecast,
    f.forecast_lower,
    f.forecast_upper,
    f.backtest_wape,
    a.actual,
    a.actual - f.forecast                as error,
    abs(a.actual - f.forecast)           as abs_error,
    {{ safe_divide('abs(a.actual - f.forecast)', 'abs(a.actual)') }} as abs_pct_error,
    case when a.actual is not null then a.actual between f.forecast_lower and f.forecast_upper end as within_interval
from forecasts as f
left join actuals as a
    on f.series = a.series
   and f.region_level = a.region_level
   and f.region_code = a.region_code
   and {{ to_date('f.week_start') }} = a.week_start
