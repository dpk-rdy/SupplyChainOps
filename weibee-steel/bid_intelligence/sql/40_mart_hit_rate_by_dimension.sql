-- Hit rate, dollars won, pricing feedback and estimating efficiency, cut five ways.
-- Decided bids only (won + lost); cancelled projects are excluded from the denominator.
create or replace table analytics.mart_hit_rate_by_dimension as
with cuts as (
    select 'project_type'    as dimension, project_type    as dimension_value, * from analytics.fct_bids
    union all
    select 'size_band',          size_band,        *        from analytics.fct_bids
    union all
    select 'distance_band',      distance_band,    *    from analytics.fct_bids
    union all
    select 'delivery_method',    delivery_method,  *  from analytics.fct_bids
    union all
    select 'state',              state,            *            from analytics.fct_bids
    union all
    select 'customer_tier',      customer_tier,    *    from analytics.fct_bids
)
select
    dimension,
    dimension_value,
    count(*)                                            as bids_submitted,
    sum(is_decided)                                     as bids_decided,
    sum(is_won)                                         as bids_won,
    sum(is_won) * 1.0 / nullif(sum(is_decided), 0)      as hit_rate_count,
    sum(case when is_decided = 1 then bid_price end)    as bid_value_decided,
    sum(case when is_won = 1 then bid_price end)        as won_value,
    sum(case when is_won = 1 then bid_price end) / nullif(sum(case when is_decided = 1 then bid_price end), 0) as hit_rate_value,
    sum(case when is_won = 1 then est_tons end)         as tons_won,
    sum(estimating_hours)                               as estimating_hours,
    sum(case when is_won = 1 then bid_price end) / nullif(sum(estimating_hours), 0) as won_value_per_est_hour,
    sum(case when result = 'lost' and lost_reason = 'price' then 1 else 0 end) as lost_on_price,
    median(price_gap_pct)                               as median_price_gap_pct,
    median(money_left_pct)                              as median_money_left_pct,
    avg(case when is_decided = 1 then markup_pct end)   as avg_markup_pct,
    avg(case when is_decided = 1 then num_bidders end)  as avg_bidders
from cuts
group by 1, 2
order by 1, 2;
