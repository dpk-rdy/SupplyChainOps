{# Straight-line distance between the customer's zip prefix and the primary
   seller's zip prefix. Used as a delivery-difficulty feature for forecasting. #}
with orders as (
    select o.order_id, c.customer_zip_prefix, ia.primary_seller_id
    from {{ ref('stg_orders') }} as o
    join {{ ref('stg_customers') }} as c using (customer_id)
    left join {{ ref('int_order_items_agg') }} as ia using (order_id)
),

sellers as (
    select seller_id, seller_zip_prefix from {{ ref('stg_sellers') }}
),

geo as (
    select zip_prefix, latitude, longitude from {{ ref('stg_geolocation_zip') }}
)

select
    o.order_id,
    cg.latitude     as customer_lat,
    cg.longitude    as customer_lng,
    sg.latitude     as seller_lat,
    sg.longitude    as seller_lng,
    case
        when cg.latitude is null or sg.latitude is null then null
        else {{ haversine_km('cg.latitude', 'cg.longitude', 'sg.latitude', 'sg.longitude') }}
    end             as distance_km
from orders as o
left join geo as cg on o.customer_zip_prefix = cg.zip_prefix
left join sellers as s on o.primary_seller_id = s.seller_id
left join geo as sg on s.seller_zip_prefix = sg.zip_prefix
