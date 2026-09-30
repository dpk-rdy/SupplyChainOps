-- Delivered orders must carry a delivery timestamp (a handful of source rows do not;
-- the threshold guards against regressions rather than the known 8 source anomalies).
select count(*) as missing
from {{ ref('fct_orders') }}
where is_delivered and delivered_at is null
having count(*) > 10
