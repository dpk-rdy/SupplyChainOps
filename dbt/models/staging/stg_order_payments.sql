with source as (
    select * from {{ source('olist', 'olist_order_payments') }}
)

select
    {{ surrogate_key(['order_id', 'payment_sequential']) }} as payment_key,
    order_id,
    payment_sequential,
    lower(payment_type)     as payment_type,
    payment_installments,
    payment_value
from source
