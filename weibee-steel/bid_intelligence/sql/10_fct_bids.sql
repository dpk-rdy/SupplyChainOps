-- One row per submitted bid, joined to its opportunity and customer, with the derived fields
-- every downstream mart re-aggregates from (never averaged ratios).
create or replace table analytics.fct_bids as
select
    b.bid_id,
    b.opportunity_id,
    o.customer_id,
    c.customer_name,
    c.tier                                              as customer_tier,
    o.project_name,
    o.project_type,
    o.city,
    o.state,
    o.distance_miles,
    case
        when o.distance_miles < 60 then '< 60 mi'
        when o.distance_miles < 150 then '60-150 mi'
        when o.distance_miles < 250 then '150-250 mi'
        else '250 mi +'
    end                                                 as distance_band,
    o.est_tons,
    case
        when o.est_tons < 100 then '< 100 t'
        when o.est_tons < 250 then '100-250 t'
        when o.est_tons < 500 then '250-500 t'
        when o.est_tons < 1000 then '500-1,000 t'
        else '1,000 t +'
    end                                                 as size_band,
    o.complexity,
    o.delivery_method,
    o.scope,
    o.lead_source,
    o.fab_start_week,
    o.fab_weeks,
    b.bid_date,
    cast(date_trunc('quarter', b.bid_date) as date)     as bid_quarter,
    year(b.bid_date)                                    as bid_year,
    b.estimator,
    b.estimating_hours,
    b.est_shop_hours,
    b.est_field_hours,
    b.est_material_cost,
    b.est_direct_cost,
    b.est_overhead,
    b.est_direct_cost + b.est_overhead                  as est_total_cost,
    b.markup_pct,
    b.bid_price,
    b.bid_price / o.est_tons                            as price_per_ton,
    (b.bid_price - b.est_direct_cost) / b.bid_price      as est_gross_margin_pct,  -- before overhead
    b.num_bidders,
    b.result,
    b.result_date,
    b.lost_reason,
    b.competitor_low_price,
    case
        when b.result = 'lost' and b.lost_reason = 'price' and b.competitor_low_price is not null
        then (b.bid_price - b.competitor_low_price) / b.bid_price
    end                                                 as price_gap_pct,
    case
        when b.result = 'won' and b.competitor_low_price is not null
        then (b.competitor_low_price - b.bid_price) / b.bid_price
    end                                                 as money_left_pct,
    case when b.result = 'won' then 1 else 0 end         as is_won,
    case when b.result in ('won', 'lost') then 1 else 0 end as is_decided
from raw.bids as b
join raw.opportunities as o using (opportunity_id)
join raw.customers as c using (customer_id);
