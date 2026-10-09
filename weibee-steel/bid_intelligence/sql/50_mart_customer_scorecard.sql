-- One row per general contractor: how often they award us, what the work is worth, how it executes,
-- and how they behave on price, change orders and payment. The relationship class is a first cut at
-- A/B/C account tiers that a business-development lead would then adjust by hand.
create or replace table analytics.mart_customer_scorecard as
with bids as (
    select
        customer_id,
        count(*)                                        as bids_submitted,
        sum(is_decided)                                 as bids_decided,
        sum(is_won)                                     as bids_won,
        sum(is_won) * 1.0 / nullif(sum(is_decided), 0)  as hit_rate_count,
        sum(case when is_decided = 1 then bid_price end) as bid_value_decided,
        sum(case when is_won = 1 then bid_price end)    as won_value,
        sum(estimating_hours)                           as estimating_hours,
        sum(case when is_won = 1 then bid_price end) / nullif(sum(estimating_hours), 0) as won_value_per_est_hour,
        sum(case when result = 'lost' and lost_reason = 'price' then 1 else 0 end) as lost_on_price,
        median(price_gap_pct)                           as median_price_gap_pct,
        avg(case when delivery_method = 'hard_bid' then 1.0 else 0.0 end) as hard_bid_share,
        min(bid_date)                                   as first_bid_date,
        max(bid_date)                                   as last_bid_date,
        mode(project_type)                              as most_common_project_type
    from analytics.fct_bids
    group by 1
),
jobs as (
    select
        customer_id,
        count(*)                                        as jobs_complete,
        sum(final_revenue)                              as revenue_complete,
        sum(final_revenue - actual_direct_cost) / nullif(sum(final_revenue), 0) as realized_gross_margin_pct,
        sum(final_revenue - actual_direct_cost) / nullif(sum(final_revenue), 0)
            - sum(bid_price - est_direct_cost) / nullif(sum(bid_price), 0)      as margin_slip_pts_weighted,
        sum(change_orders_approved) / nullif(sum(change_orders_requested), 0) as co_approval_rate,
        avg(days_to_final_payment)                      as avg_days_to_final_payment,
        avg(schedule_variance_days)                     as avg_schedule_variance_days
    from analytics.fct_jobs
    where status = 'complete'
    group by 1
),
overall as (
    select sum(final_revenue - actual_direct_cost) / sum(final_revenue) as realized_gross_margin_pct
    from analytics.fct_jobs where status = 'complete'
)
select
    c.customer_id,
    c.customer_name,
    c.hq_city,
    c.hq_state,
    c.tier,
    c.first_contact_date,
    b.* exclude (customer_id),
    j.* exclude (customer_id),
    case
        when coalesce(b.bids_decided, 0) >= 4 and b.hit_rate_count >= 0.40
             and coalesce(j.realized_gross_margin_pct, overall.realized_gross_margin_pct) >= overall.realized_gross_margin_pct - 0.02 then 'A'
        when coalesce(b.bids_decided, 0) >= 3 and b.hit_rate_count >= 0.22 then 'B'
        when coalesce(b.bids_decided, 0) < 3 then 'New / thin'
        else 'C'
    end                                                 as relationship_class
from raw.customers as c
left join bids as b using (customer_id)
left join jobs as j using (customer_id)
cross join overall
order by won_value desc nulls last;
