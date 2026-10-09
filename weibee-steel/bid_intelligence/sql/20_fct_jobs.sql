-- Executed jobs (won bids) with estimated-versus-actual performance.
create or replace table analytics.fct_jobs as
select
    j.job_id,
    f.*,
    j.fab_start_week                                    as job_fab_start_week,
    j.fab_end_week,
    j.erection_end_week,
    j.status,
    j.contract_value,
    j.actual_tons,
    j.actual_shop_hours,
    j.actual_field_hours,
    j.actual_material_cost,
    j.change_orders_requested,
    j.change_orders_approved,
    j.final_revenue,
    j.actual_direct_cost,
    j.schedule_variance_days,
    j.ncr_count,
    j.days_to_final_payment,
    case when j.status = 'complete' then (j.final_revenue - j.actual_direct_cost) / j.final_revenue end as actual_gross_margin_pct,
    case when j.status = 'complete' then f.est_gross_margin_pct - (j.final_revenue - j.actual_direct_cost) / j.final_revenue end as margin_slip_pts,
    case when j.status = 'complete' then (j.actual_shop_hours - f.est_shop_hours) / nullif(f.est_shop_hours, 0) end as shop_hours_var_pct,
    case when j.status = 'complete' and f.est_field_hours > 0 then (j.actual_field_hours - f.est_field_hours) / f.est_field_hours end as field_hours_var_pct,
    case when j.status = 'complete' then j.change_orders_approved / nullif(j.change_orders_requested, 0) end as co_approval_rate
from raw.jobs as j
join analytics.fct_bids as f using (opportunity_id);
