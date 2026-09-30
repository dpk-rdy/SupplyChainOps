-- The daily KPI mart must account for every non-canceled order exactly once.
with mart as (
    select sum(orders) as n from {{ ref('mart_kpi_daily_region') }}
),
fct as (
    select count(*) as n from {{ ref('fct_orders') }} where not is_canceled
)
select mart.n as mart_orders, fct.n as fct_orders
from mart, fct
where mart.n != fct.n
