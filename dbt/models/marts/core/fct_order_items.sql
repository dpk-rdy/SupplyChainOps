{# Grain: one row per order line item, enriched with product, seller and order context. #}
with items as (
    select * from {{ ref('stg_order_items') }}
),

orders as (
    select
        order_id, customer_state, customer_macro_region, order_status, purchased_at, purchase_date,
        purchase_week, purchase_month, is_delivered, is_on_time, delivery_days, review_score
    from {{ ref('fct_orders') }}
),

products as (
    select product_id, category_name, product_weight_g, product_volume_cm3 from {{ ref('dim_products') }}
),

sellers as (
    select seller_id, seller_state, seller_macro_region from {{ ref('dim_sellers') }}
)

select
    i.order_item_key,
    i.order_id,
    i.order_item_id,
    i.product_id,
    i.seller_id,
    p.category_name,
    s.seller_state,
    s.seller_macro_region,
    o.customer_state,
    o.customer_macro_region,
    o.order_status,
    o.is_delivered,
    o.is_on_time,
    o.purchased_at,
    o.purchase_date,
    o.purchase_week,
    o.purchase_month,
    i.shipping_limit_at,
    i.price,
    i.freight_value,
    {{ safe_divide('i.freight_value', 'i.price') }} as freight_ratio,
    p.product_weight_g,
    p.product_volume_cm3,
    o.delivery_days,
    o.review_score
from items as i
left join orders as o using (order_id)
left join products as p using (product_id)
left join sellers as s using (seller_id)
