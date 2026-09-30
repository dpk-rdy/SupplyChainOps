{# Grain: series x region x model x horizon for the most recent forecast run.
   The dashboard's "forecast accuracy" page and the assistant read this. #}
with latest_run as (
    select series, max(run_at) as run_at
    from {{ source('forecasts', 'forecast_runs') }}
    group by 1
),

accuracy as (
    select * from {{ source('forecasts', 'forecast_accuracy') }}
)

select
    a.run_id,
    a.run_at,
    a.series,
    a.region_level,
    a.region_code,
    a.model_name,
    a.is_champion,
    a.horizon_weeks,
    a.n_folds,
    a.mae,
    a.smape,
    a.wape,
    a.bias,
    a.train_end_week,
    a.n_train_weeks
from accuracy as a
join latest_run as l
    on a.series = l.series and a.run_at = l.run_at
