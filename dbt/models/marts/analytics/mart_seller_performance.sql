{# Grain: seller_id. Seller scorecard: volume, service level and economics. #}
with items as (
    select * from {{ ref('fct_order_items') }}
),

orders as (
    select order_id, is_delivered, is_on_time, delivery_days, handling_days, review_score, contribution_margin
    from {{ ref('fct_orders') }}
),

per_seller_order as (
    select
        i.seller_id,
        i.order_id,
        sum(i.price)            as gmv,
        sum(i.freight_value)    as freight_value,
        count(*)                as items
    from items as i
    group by 1, 2
)

select
    s.seller_id,
    s.seller_state,
    s.seller_macro_region,
    s.seller_city,
    count(distinct pso.order_id)                        as orders,
    sum(pso.items)                                      as items,
    sum(pso.gmv)                                        as gmv,
    sum(pso.freight_value)                              as freight_value,
    {{ safe_divide('sum(pso.gmv)', 'count(distinct pso.order_id)') }} as avg_order_gmv,
    {{ safe_divide("sum(" ~ bool_to_int('o.is_on_time') ~ ")", "sum(" ~ bool_to_int('o.is_delivered') ~ ")") }} as on_time_rate,
    avg(case when o.is_delivered then o.delivery_days end) as avg_delivery_days,
    avg(o.handling_days)                                as avg_handling_days,
    avg(o.review_score)                                 as avg_review_score,
    s.first_sale_date,
    s.last_sale_date
from {{ ref('dim_sellers') }} as s
left join per_seller_order as pso using (seller_id)
left join orders as o using (order_id)
group by 1, 2, 3, 4, s.first_sale_date, s.last_sale_date
