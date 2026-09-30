with source as (
    select * from {{ source('olist', 'olist_order_items') }}
)

select
    {{ surrogate_key(['order_id', 'order_item_id']) }} as order_item_key,
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date     as shipping_limit_at,
    price,
    freight_value
from source
