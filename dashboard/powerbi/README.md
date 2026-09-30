# Power BI setup

1. Edit `SupplyChainOps.pbids`: replace `<GCP_PROJECT>` with your project id.
2. Double-click the `.pbids` file; Power BI Desktop opens the Google BigQuery connector (sign in
   with the Google account or service account that can read the `analytics` dataset).
3. In the navigator pick `analytics.mart_kpi_daily_region`, `analytics.mart_unit_economics_monthly`,
   `analytics.mart_forecast_vs_actual`, `analytics.mart_forecast_accuracy_latest`, `analytics.dim_dates`
   and `analytics.dim_regions`. Import mode is fine (the marts are small); use DirectQuery only if you
   need live BigQuery freshness.
4. Model view: relate `mart_kpi_daily_region[date_day]` → `dim_dates[date_day]` (many-to-one) and
   `mart_kpi_daily_region[state_code]` → `dim_regions[state_code]`. Mark `dim_dates` as the date table.
5. Paste the measures from `measures.dax` into a `KPIs` measure table (Modeling → New measure).
6. Build the three pages described in `../README.md`; use the region colours listed in
   `../looker_studio/README.md` under *Theme* so both tools match.

Every ratio KPI is a DAX measure over sums, so slicing by state, region or date always
re-aggregates correctly.
