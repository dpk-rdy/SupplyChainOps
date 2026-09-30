with source as (
    select * from {{ source('olist', 'olist_products') }}
),

translation as (
    select * from {{ source('olist', 'product_category_name_translation') }}
)

select
    p.product_id,
    p.product_category_name                                     as category_name_pt,
    coalesce(t.product_category_name_english, p.product_category_name, 'unknown') as category_name,
    p.product_name_lenght                                       as product_name_length,
    p.product_description_lenght                                as product_description_length,
    p.product_photos_qty                                        as product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm,
    p.product_length_cm * p.product_height_cm * p.product_width_cm as product_volume_cm3
from source as p
left join translation as t
    on p.product_category_name = t.product_category_name
