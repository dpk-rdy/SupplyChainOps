{# Grain: purchase_week x customer_state. Input series for the demand forecast.
   Includes canceled orders as demand (they were placed), flagged separately. #}
with orders as (
    select * from {{ ref('fct_orders') }}
)

select
    purchase_week                                   as week_start,
    customer_state                                  as state_code,
    customer_macro_region                           as macro_region,
    count(*)                                        as orders,
    sum({{ bool_to_int('is_canceled') }})           as canceled_orders,
    sum(n_items)                                    as items,
    sum(gmv)                                        as gmv,
    sum(freight_value)                              as freight_value,
    count(distinct customer_unique_id)              as customers
from orders
group by 1, 2, 3
