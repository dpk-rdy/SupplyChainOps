{# Grain: purchase_month x product category. Assortment view for the dashboard and assistant. #}
with items as (
    select * from {{ ref('fct_order_items') }}
    where order_status not in ('canceled', 'unavailable')
)

select
    purchase_month                                  as month_start,
    category_name,
    count(distinct order_id)                        as orders,
    count(*)                                        as items,
    sum(price)                                      as gmv,
    sum(freight_value)                              as freight_value,
    {{ safe_divide('sum(price)', 'count(*)') }}     as avg_item_price,
    {{ safe_divide('sum(freight_value)', 'sum(price)') }} as freight_to_gmv_ratio,
    {{ safe_divide("sum(" ~ bool_to_int('is_on_time') ~ ")", "sum(" ~ bool_to_int('is_delivered') ~ ")") }} as on_time_rate,
    avg(case when is_delivered then delivery_days end) as avg_delivery_days,
    avg(review_score)                               as avg_review_score
from items
group by 1, 2
