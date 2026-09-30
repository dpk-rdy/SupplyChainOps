{# Grain: purchase_week x customer_state over delivered orders. Input series
   for the delivery-time forecast and the service-level trend charts. #}
with orders as (
    select * from {{ ref('fct_orders') }}
    where is_delivered and delivery_days is not null
)

select
    purchase_week                                   as week_start,
    customer_state                                  as state_code,
    customer_macro_region                           as macro_region,
    count(*)                                        as delivered_orders,
    avg(delivery_days)                              as avg_delivery_days,
    {{ median_of('delivery_days') }}                as median_delivery_days,
    avg(transit_days)                               as avg_transit_days,
    avg(handling_days)                              as avg_handling_days,
    avg(estimated_days)                             as avg_estimated_days,
    avg(delivery_delay_days)                        as avg_delivery_delay_days,
    avg(distance_km)                                as avg_distance_km,
    {{ safe_divide("sum(" ~ bool_to_int('is_on_time') ~ ")", 'count(*)') }} as on_time_rate
from orders
group by 1, 2, 3
