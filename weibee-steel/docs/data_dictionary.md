# Data dictionary: what the intake needs to capture

The pipeline runs on five tables. On synthetic data they come out of `bid_intelligence/synth.py`;
at Weibee Steel they would come out of the estimating log, the job-cost system and a GC/opportunity
database that this role would build. The fields marked **core** are the minimum for every mart in the
report to work; the rest sharpen it.

## customers (one row per general contractor / owner)

| field | core | notes |
|---|---|---|
| customer_id, customer_name | ✓ | one id per legal entity; branch offices as contacts, not customers |
| hq_city, hq_state | ✓ | |
| tier | | local / regional / national; drives the strategic-account flag |
| first_contact_date | | |
| primary_contact | | preconstruction lead, estimator or PM we deal with |

## opportunities (one row per project we heard about, whether or not we bid)

| field | core | notes |
|---|---|---|
| opportunity_id, project_name | ✓ | |
| customer_id | ✓ | the GC inviting us (owner-direct work gets its own customer row) |
| project_type | ✓ | warehouse, industrial, K-12, higher ed, healthcare, retail, office, church, municipal, sports, hospitality, multifamily podium |
| city, state, distance_miles | ✓ | road miles from the shop; the model uses it directly |
| est_tons | ✓ | from the takeoff, or a rough tons-per-square-foot guess at lead stage |
| complexity | ✓ | 1–5: simple braced frames … AESS / long span / heavy moment connections |
| delivery_method | ✓ | hard bid, CM at risk, negotiated, design-build |
| scope | ✓ | fab only / fab + erect |
| bid_due_date | ✓ | |
| fab_start_week, fab_weeks, erection_weeks | ✓ | expected fabrication window: drives the capacity check |
| lead_source | | GC invitation, repeat customer, lead service, architect/engineer, owner direct |
| decision, no_bid_reason | ✓ | the bid/no-bid call and why. Logging *no-bids* is what lets us learn from them |

## bids (one row per number we submitted)

| field | core | notes |
|---|---|---|
| bid_id, opportunity_id, bid_date, estimator | ✓ | |
| estimating_hours | ✓ | hours spent on the takeoff and pricing: the scarce resource the scorecard ranks against |
| est_shop_hours, est_field_hours, est_material_cost | ✓ | the estimate's cost build-up |
| est_direct_cost, est_overhead, markup_pct, bid_price | ✓ | |
| num_bidders | | from the bid tab or the GC |
| result | ✓ | won / lost / cancelled / pending |
| result_date, lost_reason | ✓ | price, relationship, schedule, scope, unknown |
| competitor_low_price | | the low number (or next-lowest when we won). Coverage of this field is itself a KPI |

## jobs (one row per won bid, filled in as the job runs and closes)

| field | core | notes |
|---|---|---|
| job_id, opportunity_id, status | ✓ | |
| fab_start_week, fab_end_week, erection_end_week | ✓ | actual windows, for the backlog chart |
| contract_value, change_orders_requested, change_orders_approved, final_revenue | ✓ | |
| actual_tons, actual_shop_hours, actual_field_hours, actual_material_cost, actual_direct_cost | ✓ | from job cost |
| schedule_variance_days, ncr_count, days_to_final_payment | | execution and customer-behaviour signals for the scorecard |

## pipeline (opportunities expected to bid in the next 6–24 months)

Same columns as `opportunities` plus `status` (lead / invited / bidding). No prices yet; the
scorecard fills in expected revenue from historical price per ton by project type.

## capacity (one row per week)

| field | notes |
|---|---|
| week_start, capacity_tons | shop throughput; changes when a shift or a line is added |

## Derived in the warehouse (`bid_intelligence/sql/`)

| table | grain | used for |
|---|---|---|
| `fct_bids` | bid | everything: size/distance bands, price gap, margin at estimate |
| `fct_jobs` | job | estimated vs actual margin and hours |
| `mart_bid_results_quarterly` | quarter | hit-rate trend |
| `mart_hit_rate_by_dimension` | dimension × value | hit rate, $ won per estimating hour, pricing feedback by type, size, distance, delivery, state, tier |
| `mart_customer_scorecard` | customer | A/B/C classes, price shoppers, CO behaviour, pay days |
| `mart_estimate_vs_actual` | dimension × value | margin slip by type, complexity, distance |
| `mart_pricing_feedback` | delivery method × gap bucket | histogram of how far off we were |
| `mart_backlog_weekly`, `mart_capacity_weekly` | week | shop load vs capacity, with the weighted pipeline |
| `pipeline_scorecard` | pipeline opportunity | the bid/no-bid ranking |
