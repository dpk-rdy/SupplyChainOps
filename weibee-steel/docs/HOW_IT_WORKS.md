# How it works (technical notes)

The full design document is [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md); this is the shorter run-and-read version.

A small, complete **data-and-decisions pipeline** for a structural-steel fabricator and erector, built
around the questions in Weibee Steel's Business Development Associate posting: bid hit rates, customer
and project-type performance, pricing feedback, estimated-versus-actual margins, a structured
bid/no-bid process, and a pipeline that can be checked against shop capacity.

```
synthetic bid history ──► DuckDB marts (SQL) ──► win-probability model ──► bid / no-bid scorecard ──► one-page HTML report
   synth.py                 sql/*.sql             win_model.py              scorecard.py                report.py + charts.py
```

**Open [`../output/bid_intelligence_report.html`](../output/bid_intelligence_report.html)** (or the [PDF](bid_intelligence_report.pdf)) for the result. Everything
in it is computed; the findings are generated from the marts, not typed in.

> **All data is synthetic.** I do not have Weibee Steel's numbers, so the generator plants the kind of
> structure a real shop has (some project types fit, some GCs award and some shop on price, odds fall
> with distance and markup, complex work overruns) and the pipeline has to recover it. The schema in
> [`data_dictionary.md`](data_dictionary.md) is what the real intake would capture; the
> business parameters in [`../bid_intelligence/config.py`](../bid_intelligence/config.py) are documented guesses.

## What it answers

| Question from the posting | Where it lives | What it does |
|---|---|---|
| Bid volume, value and **hit rates** | `mart_bid_results_quarterly`, `mart_hit_rate_by_dimension` | Count *and* dollar hit rate by quarter, project type, size band, distance band, delivery method, state, GC tier. Dollars won per estimating hour, because estimating hours are the scarce input. |
| **Customer-specific performance** | `mart_customer_scorecard` | Per GC: hit rate, value won, won $/estimating hour, median price gap when lost on price, realised margin on their jobs, change-order approval rate, days to pay. First-cut A/B/C classes and a "price shopper" flag. |
| **Pricing feedback**, why we win or lose | `fct_bids`, `mart_pricing_feedback` | Distribution of our bid vs the low number on price losses, by delivery method; "money left on the table" on wins. Coverage of the feedback field is itself tracked. |
| **Estimated vs actual** performance, gross margins | `fct_jobs`, `mart_estimate_vs_actual` | Dollar-weighted estimated vs realised gross margin and shop/field hour variance by project type, complexity, distance and tier. |
| **Bid/no-bid process** | `scorecard.py` → `pipeline_scorecard` | Every opportunity in the next 6-24 months scored on win odds, realised (not estimated) margin, estimating cost, projected shop load if won, distance and relationship. Pursue / Review / Pass with the reasons spelled out. |
| **Future project pipeline** vs capacity | `mart_backlog_weekly`, `mart_capacity_weekly` | Won work spread over fabrication windows plus the pipeline weighted by win odds, against tons/week capacity. Shows the open quarters the pipeline has to fill. |
| Estimating efficiency, **AI-assisted tools** | `scorecard.fit_estimating_effort`, model card | Hours-per-bid fitted from history; a small interpretable win model with an honest out-of-time evaluation. The same marts are the training data a takeoff or pricing tool would need. |

## Findings on the sample run (seed 5)

Pulled from `output/findings.md`; they change with the seed, which is the point.

- **Where the shop fits.** K-12, church and retail work wins 37-41 % of decided bids and gives back ≤ 3 pts of estimated margin; sports, hospitality and podium work wins 12-15 % and gives back 7-10 pts, while consuming 29 % of estimating hours for 18 % of dollars won.
- **Pricing feedback.** When we lose on price and get a number, we are a median 9.7 % high. Hard bids win 20 % against 5.6 bidders; negotiated work wins 49 %. On wins we left a median 3.9 % on the table. Feedback coverage is 62 %.
- **Price shoppers vs relationship accounts.** Seven GCs award 18 % of bids at a 10.7 % median gap: 2,650 estimating hours for $19.1M won. Four A-class accounts returned $29.4M on 1,920 hours.
- **Capacity.** Backlog covers 16 weeks. With the probability-weighted pipeline, utilisation drops below 50 % from Q1 2027; the pipeline needs roughly 9,400 more tons of identified opportunities at today's hit rate.
- **Estimate vs actual.** 22.9 % estimated gross margin, 18.3 % realised, about $4.3M over 95 jobs; complexity-5 work slips most.
- **Model.** Out-of-time AUC 0.75, Brier 0.18 vs 0.21 for guessing the base rate. Good enough to rank and budget hours; not good enough to overrule the room on one bid.

## Run it

```bash
make venv && . .venv/bin/activate      # python >= 3.11; deps: duckdb, pandas, numpy
make run                               # ~1 s: writes output/bid_intelligence_report.html + CSVs + model_card.json
make test                              # 23 tests: generator invariants, mart reconciliation, model, scorecard, end-to-end
make lint
python -m bid_intelligence run --seed 11 --out output_11   # different synthetic history, same pipeline
```

`output/warehouse.duckdb` is kept after `make run` so the marts can be queried directly:

```sql
select customer_name, hit_rate_count, won_value_per_est_hour, median_price_gap_pct, relationship_class
from analytics.mart_customer_scorecard order by won_value desc;
```

## How the decision layer works

**Win odds.** A ridge-regularised logistic regression (plain numpy, Newton's method) on tonnage, distance,
complexity, markup, bidder count, delivery method, project type, scope, and the customer's *prior*
hit rate with us, computed as of each bid date so nothing leaks from the outcome. Evaluated on bids
after a cutoff date, then re-fit on everything to score the pipeline. Coefficients are in the model card.

**Expected value.** `EV = P(win) × expected revenue × realised margin for that project type − estimating cost`,
where expected revenue is tons × historical price per ton and estimating hours come from a curve fitted
to our own bid log. Ranked per estimating hour and compared with what an hour has returned historically
(Pursue ≥ 80 %, Review ≥ 35 %, Pass below), so the thresholds re-scale with the shop's own numbers.

**Capacity check.** For each opportunity: backlog + the rest of the pipeline weighted by its odds + this
job in full, averaged over its fabrication window, against tons/week. Over 105 % is a hard flag.

**Overrides.** Low odds (< 12 %) or an overloaded shop is a Pass; a new regional/national GC on best-fit
work is kept at Review as a strategic account. The reasons column shows every flag so the bid meeting
can disagree with it, and the override should be logged as the next training data.

## Layout

```
bid_intelligence/
  config.py       business parameters and the synthetic project-type table
  synth.py        seeded generator: customers, opportunities, bids, jobs, pipeline, capacity
  warehouse.py    DuckDB loader + mart builder
  sql/            10_fct_bids … 90_mart_capacity_weekly (one mart per file, plain SQL)
  win_model.py    features, logistic regression, AUC / Brier / calibration
  scorecard.py    EV, capacity check, Pursue / Review / Pass
  insights.py     findings written from the marts
  charts.py       inline-SVG charts (no JS dependencies; native tooltips)
  report.py       the HTML page
  __main__.py     python -m bid_intelligence run
tests/            23 tests
docs/             data_dictionary.md (the intake schema), memo.md (what I would do with the real data)
output/           the rendered report, CSV exports, model card, the generated data in output/data/
```

## What I would do with the real data

Short version in [`memo.md`](memo.md): a 90-day plan that starts with the GC/opportunity
database and bid-result logging (the fields in the data dictionary), gets the marts live on the real
history, and only then turns on the scorecard.
