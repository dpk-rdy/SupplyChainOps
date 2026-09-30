with sellers as (
    select * from {{ ref('stg_sellers') }}
),

regions as (
    select * from {{ ref('dim_regions') }}
),

geo as (
    select zip_prefix, latitude, longitude from {{ ref('stg_geolocation_zip') }}
),

activity as (
    select
        i.seller_id,
        count(distinct i.order_id)          as lifetime_orders,
        sum(i.price)                        as lifetime_gmv,
        min({{ to_date('o.purchased_at') }}) as first_sale_date,
        max({{ to_date('o.purchased_at') }}) as last_sale_date
    from {{ ref('stg_order_items') }} as i
    join {{ ref('stg_orders') }} as o using (order_id)
    group by 1
)

select
    s.seller_id,
    s.seller_zip_prefix,
    s.seller_city,
    s.seller_state,
    r.state_name            as seller_state_name,
    r.macro_region          as seller_macro_region,
    g.latitude              as seller_lat,
    g.longitude             as seller_lng,
    coalesce(a.lifetime_orders, 0) as lifetime_orders,
    coalesce(a.lifetime_gmv, 0)    as lifetime_gmv,
    a.first_sale_date,
    a.last_sale_date
from sellers as s
left join regions as r on s.seller_state = r.state_code
left join geo as g on s.seller_zip_prefix = g.zip_prefix
left join activity as a using (seller_id)
