with source as (
    select * from {{ source('olist', 'olist_orders') }}
)

select
    order_id,
    customer_id,
    lower(order_status)                     as order_status,
    order_purchase_timestamp                as purchased_at,
    order_approved_at                       as approved_at,
    order_delivered_carrier_date            as delivered_to_carrier_at,
    order_delivered_customer_date           as delivered_at,
    order_estimated_delivery_date           as estimated_delivery_at,
    {{ to_date('order_purchase_timestamp') }}       as purchase_date,
    {{ to_date('order_delivered_customer_date') }}  as delivered_date,
    {{ to_date('order_estimated_delivery_date') }}  as estimated_delivery_date
from source
