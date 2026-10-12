# Tableau dashboard: build guide

Tableau cannot be scripted from this repository, so the pipeline ships the **data layer** and this
guide ships the **recipe**. Building the three dashboards below takes about 45 minutes in Tableau
Desktop or Tableau Public and needs no calculated field longer than one line.

What `make run` writes to `output/tableau/`:

| File | Use |
|---|---|
| `weibee_bid_intelligence.xlsx` | One workbook, five sheets. Connect Tableau to this. |
| `weibee_bid_intelligence.hyper` | The same five tables as a Tableau extract, if the Hyper API was installed. Faster, and what you would publish to Tableau Server or Cloud. |
| `bids_and_jobs.csv`, `customers.csv`, `pipeline_scorecard.csv`, `capacity_weekly.csv`, `capacity_long.csv` | The same tables as plain CSV. |

All numbers are from the synthetic run. Columns use plain names and labels, not keys.

## 1. Connect and model

1. Tableau: Connect to Microsoft Excel, pick `weibee_bid_intelligence.xlsx`.
2. Drag **Bids and Jobs** onto the canvas first. It is the main fact table: one row per bid, with the
   job's actuals on the same row when the bid was won and the job is complete.
3. Add **Customers** and relate on `Customer ID` = `Customer ID` (many-to-one). Do not join; use the
   relationship so customer-level measures do not duplicate.
4. **Pipeline Scorecard**, **Capacity Weekly** and **Capacity Long** stand alone. Add each as its own
   data source (Data > New Data Source) rather than relating them; they share no key with bids.
5. Set defaults: `Bid Date` as a date, `Won`, `Decided`, `Complexity`, `Bidders` as dimensions where
   you want to slice and measures where you want to sum (Tableau will guess measures for all of them;
   convert `Complexity` to a dimension).

## 2. Calculated fields

Create these on **Bids and Jobs** unless noted. Every ratio is a sum over a sum, so it stays correct
at any level of aggregation.

| Name | Formula | Format |
|---|---|---|
| Hit Rate | `SUM([Won]) / SUM([Decided])` | percentage, 0 dp |
| Hit Rate by Value | `SUM([Won Value]) / SUM([Bid Value if Decided])` | percentage |
| Won $ per Est Hour | `SUM([Won Value]) / SUM([Estimating Hours])` | currency, 0 dp |
| Est Gross Margin % (jobs) | `SUM(IF [Job Status] = "Complete" THEN [Bid Price] - [Est Direct Cost] END) / SUM(IF [Job Status] = "Complete" THEN [Bid Price] END)` | percentage, 1 dp |
| Realised Gross Margin % | `SUM([Final Revenue] - [Actual Direct Cost]) / SUM([Final Revenue])` | percentage, 1 dp |
| Margin Slip (pts) | `([Est Gross Margin % (jobs)] - [Realised Gross Margin %]) * 100` | number, 1 dp |
| Median Price Gap | `MEDIAN([Price Gap %])` | percentage, 1 dp |
| Price Feedback Coverage | `SUM(IF NOT ISNULL([Price Gap %]) THEN 1 END) / SUM(IF [Result] = "Lost" AND [Lost Reason] = "Price" THEN 1 END)` | percentage |
| Lost on Price | `SUM(IF [Result] = "Lost" AND [Lost Reason] = "Price" THEN 1 ELSE 0 END)` | number |
| Trailing 12 Months | `[Bid Date] > DATEADD('year', -1, [Snapshot Date])` | boolean, use as a filter |
| Decided Bid | `[Decided] = 1` | boolean, use as a filter |

Create one **parameter** first: `Snapshot Date`, date, default `2026-09-28`. On real data make it
`TODAY()` inside the calculation instead.

On **Capacity Weekly**:

| Name | Formula |
|---|---|
| Projected Utilisation | `SUM([Backlog (tons)] + [Weighted Pipeline (tons)]) / SUM([Capacity (tons)])` |
| Future Week | `[Week] >= [Snapshot Date]` (recreate the parameter in this source or copy it) |

On **Pipeline Scorecard**:

| Name | Formula |
|---|---|
| Call Colour | `[Recommendation]` (use as colour; assign green, amber, grey in the legend) |
| Pursue Hours | `SUM(IF [Recommendation] = "Pursue" THEN [Estimating Hours] END)` |

## 3. Worksheets

Build each as its own sheet; names in bold are what the dashboards reference.

**KPI tiles** (six sheets, each a single text mark, filter Trailing 12 Months = True where noted):

| Sheet | Measure | Filter | Subtitle text |
|---|---|---|---|
| **KPI Hit Rate** | Hit Rate | Trailing 12 Months, Decided Bid | `SUM([Won])` of `SUM([Decided])` decided bids |
| **KPI Value Won** | `SUM([Won Value])` | Trailing 12 Months | `SUM([Won Tons])` tons |
| **KPI Margin Slip** | Margin Slip (pts) | none | estimated / realised percentages |
| **KPI Backlog Weeks** | from Capacity Weekly: `SUM(IF [Future Week] THEN [Backlog (tons)] END) / 140` | none | tons at 140 tons a week |
| **KPI Shop Load** | from Capacity Weekly: Projected Utilisation | Future Week and `Week < DATEADD('week', 52, [Snapshot Date])` | next 52 weeks |
| **KPI Pursue** | from Pipeline Scorecard: `COUNTD(IF [Recommendation] = "Pursue" THEN [Opportunity ID] END)` | none | of `COUNTD([Opportunity ID])` opportunities |

**Hit Rate Trend**: Columns `QUARTER(Bid Date)` continuous; Rows `Hit Rate` and `Hit Rate by Value`
as two measures on one axis (Measure Values, not dual axis); Marks line; filter Decided Bid. Add a
constant reference line at the overall hit rate.

**Hit Rate by Project Type**: Rows `Project Type` sorted descending by Hit Rate; Columns `Hit Rate`;
Marks bar, colour fixed blue; label Hit Rate; tooltip add `SUM([Won])`, `SUM([Decided])`,
`SUM([Won Value])`, Won $ per Est Hour. Add an average reference line. Duplicate this sheet three
times swapping the row to **Size Band**, **Distance Band**, **Delivery Method** (sort Size and
Distance bands manually).

**Won $ per Estimating Hour**: same as above with Won $ per Est Hour, colour fixed green.

**Estimate vs Actual by Type** (barbell): Rows `Project Type`; Columns `Est Gross Margin % (jobs)`
and `Realised Gross Margin %` on a dual axis, synchronised; first axis Marks circle blue, second
Marks circle orange; add a third measure `Measure Values` as a line between them if you want the bar
(Marks line, Path = Measure Names). Filter `Job Status` = Complete. Label the realised circle with
Margin Slip (pts).

**Price Gap Histogram**: create bins on `Price Gap %` (size 0.02); Columns the bin; Rows `COUNT([Bid ID])`;
colour fixed purple; filter `Price Gap %` not null. Tooltip add `Delivery Method`.

**Customer Scorecard**: a text table. Rows `Customer`, `Tier`, `Relationship Class`; Measure Values:
`SUM([Bids Decided])`, Hit Rate, `SUM([Won Value])`, Won $ per Est Hour, Median Price Gap,
Realised Gross Margin %, `AVG([CO Approval Rate])` (from Customers), `AVG([Avg Days to Pay])`.
Sort by Won Value descending. Colour the Relationship Class cell: A blue, B grey, C orange.

**Shop Load** (from Capacity Long): Columns `WEEK(Week)` continuous; Rows `SUM([Tons])`; Marks area,
Colour `Load Type` (Backlog blue, Weighted Pipeline amber, Open Capacity light grey); stack marks on.
Filter Week between 26 weeks before and 78 weeks after the snapshot. Add a reference line at
`SUM([Capacity (tons)])` per week (or a constant 140) in black, dashed. Add a reference line at the
Snapshot Date on the x axis labelled "today".

**Shop Load by Quarter** (from Capacity Weekly): Rows `QUARTER(Week)`; Measure Values
`AVG([Backlog (tons)])`, `AVG([Weighted Pipeline (tons)])`, Projected Utilisation; filter Future Week.

**Scorecard Summary** (Pipeline Scorecard): Rows `Recommendation` sorted Pursue, Review, Pass;
Measure Values `COUNTD([Opportunity ID])`, `SUM([Estimating Hours])`, `SUM([Tons])`,
`SUM([Expected Value])`. Colour rows by Call Colour.

**Ranked Opportunities** (Pipeline Scorecard): text table. Rows `Rank`, `Recommendation`, `Project`,
`Customer`, `Project Type`, `Delivery Method`; Measure Values `SUM([Tons])`, `SUM([Distance (mi)])`,
`SUM([Win Odds])`, `SUM([EV per Est Hour])`, `SUM([Shop Load if Won])`, and `ATTR([Reasons])`.
Sort by Rank. Colour the Recommendation cell by Call Colour. Put `Recommendation`, `Project Type`,
`Customer`, `QUARTER(Bid Due)` on Filters and show them as dashboard filters.

**Odds vs Value** (Pipeline Scorecard): scatter. Columns `SUM([Win Odds])`; Rows `SUM([EV per Est Hour])`;
Detail `Opportunity ID`; Size `SUM([Tons])`; Colour Call Colour; Shape by `Delivery Method` if you
like. Reference lines at Win Odds 0.12 and at 0.8 and 0.35 times the historical yardstick
(about $2,500 per hour on the sample run: read the exact value from `model_card.json` or the report).
Tooltip: Project, Customer, Reasons.

## 4. Dashboards

Size 1400 x 900 (or Automatic for Tableau Public). Use a light background and keep the palette:
blue `#2A78D6` estimate / won / backlog, orange `#EB6834` actual, amber `#EDA100` pipeline, green
`#1BAF7A` Pursue, grey Pass. Titles are sentences, not labels.

**Dashboard 1: The business at a glance**
Top row: the six KPI tiles, equal width. Second row: Hit Rate Trend (left two thirds) and
Scorecard Summary (right third). Third row: Hit Rate by Project Type (left) and Shop Load (right).
One global filter: Trailing 12 Months on the tiles only (do not apply it to the trend).

**Dashboard 2: Where we win and what it earns**
Left column: Hit Rate by Project Type, Size Band, Distance Band, Delivery Method as a 2 x 2 grid.
Right column top: Estimate vs Actual by Type. Right column bottom: Price Gap Histogram.
Full width bottom: Customer Scorecard with a Customer search filter. Filter actions: clicking a
project-type bar filters the customer table and the barbell.

**Dashboard 3: Bid / no-bid**
Top: Scorecard Summary (left) and Odds vs Value (right). Bottom: Ranked Opportunities, full width,
with Recommendation, Project Type, Customer and Bid Due quarter as filters on the right edge.
A highlight action from the scatter to the table. Add a text object with the one-line definition:
"EV = win odds x expected revenue x margin we actually realise on that project type, minus
estimating cost; ranked per estimating hour against the historical return."

## 5. Publishing

- **Tableau Public**: File > Save to Tableau Public. The workbook must use an extract; Tableau will
  create one from the Excel source. All data is synthetic, so publishing is safe. Hide the data
  sheets if you do not want the raw tables downloadable.
- **Tableau Server or Cloud**: publish the `.hyper` as a data source first, then the workbook against
  it. On real data, schedule `make run` and republish the extract on the same cadence.

## 6. Keeping it in sync with the pipeline

The report, the deck numbers and these tables all come from the same marts. When the SQL changes,
`make run` rewrites `output/tableau/` and a Tableau workbook pointed at the Excel file picks up the
new columns on refresh. Keep calculated fields as sum-over-sum on the exported columns and nothing
in Tableau needs to know how the marts were built.
