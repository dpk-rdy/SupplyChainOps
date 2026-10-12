-- Shop load from won work, spread evenly over each job's fabrication window, against capacity.
create or replace table analytics.mart_backlog_weekly as
select
    cap.week_start,
    cap.capacity_tons,
    coalesce(sum(o.est_tons / o.fab_weeks), 0)          as backlog_tons,
    count(j.job_id)                                     as jobs_in_shop
from raw.capacity as cap
left join raw.jobs as j
    on cap.week_start >= j.fab_start_week and cap.week_start < j.fab_end_week
left join raw.opportunities as o using (opportunity_id)
group by 1, 2
order by 1;
