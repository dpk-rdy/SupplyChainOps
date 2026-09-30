{# One representative point per zip-code prefix (the raw file has ~1M points).
   Outlier coordinates outside Brazil's bounding box are dropped first. #}
with source as (
    select * from {{ source('olist', 'olist_geolocation') }}
    where geolocation_lat between -34.0 and 6.0
      and geolocation_lng between -74.0 and -34.0
)

select
    geolocation_zip_code_prefix     as zip_prefix,
    avg(geolocation_lat)            as latitude,
    avg(geolocation_lng)            as longitude,
    min(lower(geolocation_city))    as city,
    min(upper(geolocation_state))   as state,
    count(*)                        as n_points
from source
group by 1
