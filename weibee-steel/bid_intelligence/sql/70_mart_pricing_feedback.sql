-- Where our number landed relative to the low bid when we lost on price, by delivery method.
create or replace table analytics.mart_pricing_feedback as
select
    delivery_method,
    case
        when price_gap_pct < 0.02 then '0-2 %'
        when price_gap_pct < 0.04 then '2-4 %'
        when price_gap_pct < 0.06 then '4-6 %'
        when price_gap_pct < 0.08 then '6-8 %'
        when price_gap_pct < 0.10 then '8-10 %'
        when price_gap_pct < 0.15 then '10-15 %'
        else '15 % +'
    end                                                 as gap_bucket,
    count(*)                                            as bids_lost_on_price,
    sum(bid_price)                                      as bid_value
from analytics.fct_bids
where price_gap_pct is not null
group by 1, 2
order by 1, 2;
