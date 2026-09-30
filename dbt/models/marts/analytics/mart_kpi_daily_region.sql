{# Grain: purchase_date x customer_state. Daily operations KPIs used by the
   dashboard. Delivery KPIs (on-time rate, delivery days) are computed over
   delivered orders only; volume and economics over all non-canceled orders. #}
with orders as (
    select * from {{ ref('fct_orders') }}
)

select
    purchase_date                                               as date_day,
    customer_state                                              as state_code,
    customer_macro_region                                       as macro_region,

    -- volume
    count(*)                                                    as orders,
    sum({{ bool_to_int('is_delivered') }})                      as delivered_orders,
    sum({{ bool_to_int('is_canceled') }})                       as canceled_orders,
    sum(n_items)                                                as items,
    count(distinct customer_unique_id)                          as customers,

    -- service level
    sum({{ bool_to_int('is_on_time') }})                        as on_time_orders,
    sum({{ bool_to_int('is_on_time = false') }})                as late_orders,
    {{ safe_divide("sum(" ~ bool_to_int('is_on_time') ~ ")", "sum(" ~ bool_to_int('is_delivered') ~ ")") }} as on_time_rate,
    avg(case when is_delivered then delivery_days end)          as avg_delivery_days,
    avg(case when is_delivered then delivery_delay_days end)    as avg_delivery_delay_days,
    avg(estimated_days)                                         as avg_estimated_days,
    avg(review_score)                                           as avg_review_score,

    -- money (BRL)
    sum(gmv)                                                    as gmv,
    sum(freight_value)                                          as freight_revenue,
    sum(take_revenue)                                           as take_revenue,
    sum(platform_revenue)                                       as platform_revenue,
    sum(delivery_cost)                                          as delivery_cost,
    sum(payment_fee)                                            as payment_fees,
    sum(handling_cost)                                          as handling_cost,
    sum(platform_cost)                                          as platform_cost,
    sum(contribution_margin)                                    as contribution_margin,

    -- unit economics
    {{ safe_divide('sum(contribution_margin)', 'count(*)') }}   as margin_per_order,
    {{ safe_divide('sum(gmv)', 'count(*)') }}                   as avg_order_value,
    {{ safe_divide("sum(case when is_delivered then delivery_cost end)", "sum(" ~ bool_to_int('is_delivered') ~ ")") }} as cost_per_delivery,
    {{ safe_divide('sum(freight_value)', 'sum(gmv)') }}         as freight_to_gmv_ratio
from orders
where not is_canceled
group by 1, 2, 3
