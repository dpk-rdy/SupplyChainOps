{# Order-level roll-up of line items. #}
with items as (
    select * from {{ ref('stg_order_items') }}
),

products as (
    select product_id, product_weight_g, product_volume_cm3, category_name
    from {{ ref('stg_products') }}
),

joined as (
    select
        i.*,
        p.product_weight_g,
        p.product_volume_cm3,
        p.category_name
    from items as i
    left join products as p using (product_id)
),

primary_seller as (
    {# The seller of the first line item is treated as the order's primary seller. #}
    select order_id, seller_id, category_name
    from joined
    where order_item_id = 1
)

select
    j.order_id,
    count(*)                                as n_items,
    count(distinct j.product_id)            as n_distinct_products,
    count(distinct j.seller_id)             as n_sellers,
    sum(j.price)                            as gmv,
    sum(j.freight_value)                    as freight_value,
    sum(coalesce(j.product_weight_g, 0))    as total_weight_g,
    sum(coalesce(j.product_volume_cm3, 0))  as total_volume_cm3,
    max(j.shipping_limit_at)                as shipping_limit_at,
    min(ps.seller_id)                       as primary_seller_id,
    min(ps.category_name)                   as primary_category_name
from joined as j
left join primary_seller as ps using (order_id)
group by 1
