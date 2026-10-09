# Memo: from this sample to Weibee Steel's real data

**To:** Weibee Steel leadership · **Re:** what the bid-intelligence pipeline would look like on our own history

## The idea in one paragraph

Weibee Steel already generates every number this report needs: every invitation, every takeoff hour,
every bid, every award letter, every job-cost close-out. Today they live in estimators' heads, email
threads and the accounting system. Putting them in one structured table per event (customer,
opportunity, bid, job) and re-computing a handful of marts every week turns "we do well on schools"
into a hit rate with a denominator, a realised margin and a dollars-per-estimating-hour figure that
the bid meeting can act on. The scorecard is the last step, not the first; it is only as good as the
bid results and low-bid numbers we collect.

## First 90 days

**Weeks 1–4: learn the shop, build the intake.**
Shadow estimating, PM, QC, shop and field as the posting describes. While doing it, build the
GC/opportunity database with the fields in `docs/data_dictionary.md`, starting from the last 3 years
of bid logs and job-cost closes. Backfill `result`, `lost_reason` and `competitor_low_price` by
calling the GCs we lost to; coverage of that one field is the first KPI I would report.

**Weeks 5–8: get the marts live on real history.**
Point `bid_intelligence/sql/` at the real tables (DuckDB on a shared drive is enough to start; the SQL
ports to anything). Publish the hit-rate, customer and estimate-vs-actual pages first and sit with
the estimators and PMs to argue with the numbers until the definitions are right: what counts as a
decided bid, which overhead sits in "direct cost", how a change order is booked.

**Weeks 9–13: structured bid/no-bid.**
Turn on the scorecard for the weekly bid meeting with the recommendation shown *next to* the inputs,
never alone. Log the room's override and why. Set the estimating-hour budget per quarter and let the
ranking allocate it. Start the pipeline table for 6–24 months out and review the capacity chart
monthly with shop leadership.

## What changes in the pipeline with real data

| Sample | Real |
|---|---|
| `synth.py` generates history | Estimating log + job cost + GC database, loaded by `warehouse.load_raw` from CSV or a database |
| Capacity is a constant | Shop calendar from scheduling, including shifts and outsourced fabrication |
| Price per ton by project type | Actual estimate when one exists; type median only at lead stage |
| Realised margin by type | Add estimator, PM and erection crew as dimensions once there are enough jobs |
| Logistic regression, re-fit quarterly | Same; add a "relationship contact changed" flag and bid-tab bidder lists when available |

## Technology I would evaluate, in this order

1. **A GC/opportunity CRM-lite** (could be a spreadsheet with discipline, then Airtable/HubSpot/Unanet-style tooling) so the intake survives staff changes.
2. **Automated takeoff** (e.g. model-based quantity extraction from IFC/Revit, or AI-assisted PDF takeoff) measured against the fitted estimating-hours curve: the tool pays for itself only if hours-per-bid drop on the project types we actually pursue.
3. **Lead services** (Dodge, ConstructConnect, BuildCentral) scored through the same scorecard, so we buy leads where the model says we win.
4. **Pricing feedback automation**: a post-award email template and a field in the database, before any software.

## What this sample does not do

- It uses synthetic data; the findings are illustrative of *kind*, not of Weibee Steel.
- It treats estimating hours as the only scarce input. Real bid/no-bid also weighs bonding capacity,
  cash flow, crew availability and the GC's schedule risk; those belong in the reasons column once
  the data exists.
- The win model is small on purpose. With a few hundred bids a bigger model would mostly learn noise.
