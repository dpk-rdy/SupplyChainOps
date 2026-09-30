with payments as (
    select * from {{ ref('stg_order_payments') }}
),

first_payment as (
    select order_id, payment_type
    from payments
    where payment_sequential = 1
)

select
    p.order_id,
    sum(p.payment_value)                as payment_value,
    count(*)                            as n_payments,
    max(p.payment_installments)         as max_installments,
    min(fp.payment_type)                as primary_payment_type,
    sum({{ bool_to_int("p.payment_type = 'voucher'") }} * p.payment_value) as voucher_value
from payments as p
left join first_payment as fp using (order_id)
group by 1
