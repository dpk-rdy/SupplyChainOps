{# Grain: one row per order. The central fact table: delivery timing, service
   levels and unit economics. Cost lines are modelled from the assumptions in
   dbt_project.yml vars because Olist publishes no cost data. #}
{% set take_rate = var('marketplace_take_rate') %}
{% set fee_rate = var('payment_processing_rate') %}
{% set delivery_ratio = var('delivery_cost_ratio') %}
{% set handling_order = var('handling_cost_per_order') %}
{% set handling_item = var('handling_cost_per_extra_item') %}

with orders as (
    select * from {{ ref('stg_orders') }}
),

customers as (
    select * from {{ ref('dim_customers') }}
),

items as (
    select * from {{ ref('int_order_items_agg') }}
),

payments as (
    select * from {{ ref('int_order_payments_agg') }}
),

reviews as (
    select * from {{ ref('int_order_reviews_latest') }}
),

distance as (
    select order_id, distance_km from {{ ref('int_order_distance') }}
),

sellers as (
    select seller_id, seller_state, seller_macro_region from {{ ref('dim_sellers') }}
),

base as (
    select
        o.order_id,
        o.customer_id,
        c.customer_unique_id,
        c.customer_state,
        c.customer_macro_region,
        c.customer_city,
        i.primary_seller_id,
        s.seller_state,
        s.seller_macro_region,
        i.primary_category_name,
        o.order_status,
        o.purchased_at,
        o.purchase_date,
        {{ week_start('o.purchase_date') }}     as purchase_week,
        {{ month_start('o.purchase_date') }}    as purchase_month,
        o.approved_at,
        o.delivered_to_carrier_at,
        o.delivered_at,
        o.delivered_date,
        o.estimated_delivery_at,
        o.estimated_delivery_date,

        -- status flags
        o.order_status = 'delivered'                    as is_delivered,
        o.order_status in ('canceled', 'unavailable')   as is_canceled,

        -- timing (fractional days)
        {{ hours_between('o.purchased_at', 'o.approved_at') }}                  as approval_hours,
        {{ days_between('o.approved_at', 'o.delivered_to_carrier_at') }}        as handling_days,
        {{ days_between('o.delivered_to_carrier_at', 'o.delivered_at') }}       as transit_days,
        {{ days_between('o.purchased_at', 'o.delivered_at') }}                  as delivery_days,
        {{ days_between('o.purchased_at', 'o.estimated_delivery_at') }}         as estimated_days,
        {{ days_between('o.estimated_delivery_at', 'o.delivered_at') }}         as delivery_delay_days,
        {{ days_between('i.shipping_limit_at', 'o.delivered_to_carrier_at') }}  as carrier_handover_delay_days,

        -- basket
        coalesce(i.n_items, 0)              as n_items,
        coalesce(i.n_sellers, 0)            as n_sellers,
        coalesce(i.gmv, 0)                  as gmv,
        coalesce(i.freight_value, 0)        as freight_value,
        coalesce(i.total_weight_g, 0)       as total_weight_g,
        coalesce(p.payment_value, 0)        as payment_value,
        p.primary_payment_type,
        p.max_installments,
        r.review_score,
        d.distance_km
    from orders as o
    left join customers as c using (customer_id)
    left join items as i using (order_id)
    left join payments as p using (order_id)
    left join reviews as r using (order_id)
    left join distance as d using (order_id)
    left join sellers as s on i.primary_seller_id = s.seller_id
),

economics as (
    select
        *,
        -- Service level: an order is on time when it reached the customer no later
        -- than the estimated delivery date (date granularity, as promised to the customer).
        case
            when is_delivered and delivered_at is not null and estimated_delivery_at is not null
                then delivered_date <= estimated_delivery_date
        end                                                     as is_on_time,

        -- Revenue lines
        gmv * {{ take_rate }}                                   as take_revenue,
        freight_value                                           as freight_revenue,
        -- Cost lines
        freight_value * {{ delivery_ratio }}                    as delivery_cost,
        payment_value * {{ fee_rate }}                          as payment_fee,
        {{ handling_order }} + greatest(n_items - 1, 0) * {{ handling_item }} as handling_cost
    from base
)

select
    *,
    take_revenue + freight_revenue                              as platform_revenue,
    delivery_cost + payment_fee + handling_cost                 as platform_cost,
    (take_revenue + freight_revenue) - (delivery_cost + payment_fee + handling_cost) as contribution_margin,
    case when is_delivered then delivery_cost end               as cost_per_delivery
from economics
