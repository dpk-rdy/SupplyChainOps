with spine as (
    {{ date_spine(var('date_spine_start'), var('date_spine_end')) }}
)

select
    date_day,
    extract(year from date_day)         as year,
    extract(quarter from date_day)      as quarter,
    extract(month from date_day)        as month,
    {{ month_start('date_day') }}       as month_start,
    {{ week_start('date_day') }}        as week_start,
    {{ iso_day_of_week('date_day') }}   as iso_day_of_week,
    {{ iso_day_of_week('date_day') }} >= 6 as is_weekend
from spine
