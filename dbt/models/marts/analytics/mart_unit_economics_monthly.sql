{# Grain: purchase_month x customer_state. Monthly P&L view per order for the
   unit-economics dashboard page. #}
with orders as (
    select * from {{ ref('fct_orders') }}
    where not is_canceled
)

select
    purchase_month                                              as month_start,
    customer_state                                              as state_code,
    customer_macro_region                                       as macro_region,
    count(*)                                                    as orders,
    sum(n_items)                                                as items,
    sum({{ bool_to_int('is_delivered') }})                      as delivered_orders,

    sum(gmv)                                                    as gmv,
    sum(take_revenue)                                           as take_revenue,
    sum(freight_revenue)                                        as freight_revenue,
    sum(platform_revenue)                                       as platform_revenue,
    sum(delivery_cost)                                          as delivery_cost,
    sum(payment_fee)                                            as payment_fees,
    sum(handling_cost)                                          as handling_cost,
    sum(platform_cost)                                          as platform_cost,
    sum(contribution_margin)                                    as contribution_margin,

    {{ safe_divide('sum(gmv)', 'count(*)') }}                   as avg_order_value,
    {{ safe_divide('sum(n_items)', 'count(*)') }}               as items_per_order,
    {{ safe_divide('sum(platform_revenue)', 'count(*)') }}      as revenue_per_order,
    {{ safe_divide('sum(platform_cost)', 'count(*)') }}         as cost_per_order,
    {{ safe_divide('sum(contribution_margin)', 'count(*)') }}   as margin_per_order,
    {{ safe_divide('sum(contribution_margin)', 'sum(platform_revenue)') }} as contribution_margin_pct,
    {{ safe_divide("sum(case when is_delivered then delivery_cost end)", "sum(" ~ bool_to_int('is_delivered') ~ ")") }} as cost_per_delivery,
    {{ safe_divide('sum(freight_value)', 'sum(gmv)') }}         as freight_to_gmv_ratio,
    {{ safe_divide("sum(" ~ bool_to_int('is_on_time') ~ ")", "sum(" ~ bool_to_int('is_delivered') ~ ")") }} as on_time_rate,
    avg(case when is_delivered then delivery_days end)          as avg_delivery_days
from orders
group by 1, 2, 3
