-- Estimated versus actual gross margin and hours on completed jobs, by project type, complexity,
-- distance and customer tier. Margins are dollar-weighted (sum/sum), never averaged.
create or replace table analytics.mart_estimate_vs_actual as
with cuts as (
    select 'project_type'  as dimension, project_type              as dimension_value, *  from analytics.fct_jobs
    union all
    select 'complexity',      'complexity ' || cast(complexity as varchar), * from analytics.fct_jobs
    union all
    select 'distance_band',   distance_band,            * from analytics.fct_jobs
    union all
    select 'customer_tier',   customer_tier,            * from analytics.fct_jobs
    union all
    select 'all',             'all jobs',               *                         from analytics.fct_jobs
)
select
    dimension,
    dimension_value,
    count(*)                                            as jobs_complete,
    sum(final_revenue)                                  as revenue,
    sum(bid_price - est_direct_cost) / nullif(sum(bid_price), 0)           as est_gross_margin_pct,
    sum(final_revenue - actual_direct_cost) / nullif(sum(final_revenue), 0) as actual_gross_margin_pct,
    sum(bid_price - est_direct_cost) / nullif(sum(bid_price), 0)
        - sum(final_revenue - actual_direct_cost) / nullif(sum(final_revenue), 0) as margin_slip_pts,
    sum(actual_shop_hours - est_shop_hours) / nullif(sum(est_shop_hours), 0)   as shop_hours_var_pct,
    sum(actual_field_hours - est_field_hours) / nullif(sum(est_field_hours), 0) as field_hours_var_pct,
    sum(change_orders_approved) / nullif(sum(change_orders_requested), 0)      as co_approval_rate,
    avg(schedule_variance_days)                         as avg_schedule_variance_days,
    sum(ncr_count) * 100.0 / nullif(sum(actual_tons), 0) as ncr_per_100_tons
from cuts
where status = 'complete'
group by 1, 2
order by 1, 2;
