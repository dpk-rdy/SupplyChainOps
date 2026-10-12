-- Backlog plus probability-weighted pipeline load, built after the scorecard is written.
create or replace table analytics.mart_capacity_weekly as
select
    b.week_start,
    b.capacity_tons,
    b.backlog_tons,
    b.jobs_in_shop,
    coalesce(sum(s.p_win * p.est_tons / p.fab_weeks), 0)  as weighted_pipeline_tons,
    (b.backlog_tons + coalesce(sum(s.p_win * p.est_tons / p.fab_weeks), 0)) / b.capacity_tons as projected_utilisation
from analytics.mart_backlog_weekly as b
left join raw.pipeline as p
    on b.week_start >= p.fab_start_week and b.week_start < p.fab_start_week + interval (p.fab_weeks) week
left join analytics.pipeline_scorecard as s using (opportunity_id)
group by 1, 2, 3, 4
order by 1;
