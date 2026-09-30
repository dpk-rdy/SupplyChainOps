-- contribution_margin must equal revenue minus cost on every order (floating tolerance).
select order_id
from {{ ref('fct_orders') }}
where abs(contribution_margin - (platform_revenue - platform_cost)) > 0.001
