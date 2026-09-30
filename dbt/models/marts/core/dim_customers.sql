with customers as (
    select * from {{ ref('stg_customers') }}
),

regions as (
    select * from {{ ref('dim_regions') }}
),

geo as (
    select zip_prefix, latitude, longitude from {{ ref('stg_geolocation_zip') }}
)

select
    c.customer_id,
    c.customer_unique_id,
    c.customer_zip_prefix,
    c.customer_city,
    c.customer_state,
    r.state_name        as customer_state_name,
    r.macro_region      as customer_macro_region,
    g.latitude          as customer_lat,
    g.longitude         as customer_lng
from customers as c
left join regions as r on c.customer_state = r.state_code
left join geo as g on c.customer_zip_prefix = g.zip_prefix
