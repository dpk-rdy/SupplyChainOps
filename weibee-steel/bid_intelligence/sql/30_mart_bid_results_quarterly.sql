-- Bid volume, hit rate by count and by dollar, and estimating effort per quarter.
create or replace table analytics.mart_bid_results_quarterly as
select
    bid_quarter,
    count(*)                                            as bids_submitted,
    sum(is_decided)                                     as bids_decided,
    sum(is_won)                                         as bids_won,
    sum(is_won) * 1.0 / nullif(sum(is_decided), 0)      as hit_rate_count,
    sum(case when is_decided = 1 then bid_price end)    as bid_value_decided,
    sum(case when is_won = 1 then bid_price end)        as won_value,
    sum(case when is_won = 1 then bid_price end) / nullif(sum(case when is_decided = 1 then bid_price end), 0) as hit_rate_value,
    sum(case when is_decided = 1 then est_tons end)     as tons_bid,
    sum(case when is_won = 1 then est_tons end)         as tons_won,
    sum(estimating_hours)                               as estimating_hours,
    sum(case when is_won = 1 then bid_price end) / nullif(sum(estimating_hours), 0) as won_value_per_est_hour
from analytics.fct_bids
group by 1
order by 1;
