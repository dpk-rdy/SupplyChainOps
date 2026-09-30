select
    state_code,
    state_name,
    macro_region,
    capital_city
from {{ ref('brazil_states') }}
