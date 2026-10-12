"""Tableau-ready data layer.

Writes one Excel workbook (one sheet per table, friendly column names, labels instead of keys), the
same tables as CSV, and, when the Tableau Hyper API is installed, a single .hyper extract. The build
recipe for the dashboards themselves is in docs/TABLEAU_GUIDE.md.

Tableau prefers long, denormalised tables with human-readable headers, so this module does the joins
and the labelling once, and every calculated field in the guide is a sum-over-sum on these columns.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bid_intelligence import config as C
from bid_intelligence import warehouse as W

TYPE_LABEL = {p.key: p.label for p in C.PROJECT_TYPES}
METHOD_LABEL = {k: v[0] for k, v in C.DELIVERY_METHODS.items()}
RESULT_LABEL = {"won": "Won", "lost": "Lost", "cancelled": "Cancelled", "pending": "Pending"}


def bids_and_jobs(con) -> pd.DataFrame:
    f = W.df(con, "select * from analytics.fct_bids")
    j = W.df(
        con,
        """select opportunity_id, job_id, status as job_status, fab_end_week, erection_end_week,
                  final_revenue, actual_direct_cost, actual_gross_margin_pct, margin_slip_pts,
                  shop_hours_var_pct, field_hours_var_pct, change_orders_requested, change_orders_approved,
                  schedule_variance_days, ncr_count, days_to_final_payment
           from analytics.fct_jobs""",
    )
    cs = W.df(con, "select customer_id, relationship_class from analytics.mart_customer_scorecard")
    d = f.merge(j, on="opportunity_id", how="left").merge(cs, on="customer_id", how="left")
    out = pd.DataFrame(
        {
            "Bid ID": d.bid_id,
            "Opportunity ID": d.opportunity_id,
            "Bid Date": pd.to_datetime(d.bid_date),
            "Bid Quarter": pd.to_datetime(d.bid_quarter),
            "Bid Year": d.bid_year,
            "Customer ID": d.customer_id,
            "Customer": d.customer_name,
            "Customer Tier": d.customer_tier.str.title(),
            "Relationship Class": d.relationship_class,
            "Project": d.project_name,
            "Project Type": d.project_type.map(TYPE_LABEL),
            "City": d.city,
            "State": d.state,
            "Distance (mi)": d.distance_miles,
            "Distance Band": d.distance_band,
            "Tons": d.est_tons,
            "Size Band": d.size_band,
            "Complexity": d.complexity,
            "Delivery Method": d.delivery_method.map(METHOD_LABEL),
            "Scope": d.scope.map({"fab_erect": "Fab + erect", "fab_only": "Fab only"}),
            "Lead Source": d.lead_source,
            "Estimator": d.estimator,
            "Estimating Hours": d.estimating_hours,
            "Est Direct Cost": d.est_direct_cost,
            "Est Overhead": d.est_overhead,
            "Markup %": d.markup_pct,
            "Bid Price": d.bid_price,
            "Price per Ton": d.price_per_ton,
            "Est Gross Margin %": d.est_gross_margin_pct,
            "Bidders": d.num_bidders,
            "Result": d.result.map(RESULT_LABEL),
            "Result Date": pd.to_datetime(d.result_date),
            "Decided": d.is_decided,
            "Won": d.is_won,
            "Lost Reason": d.lost_reason.fillna("").str.replace("_", " ").str.capitalize().replace("", None),
            "Competitor Low Price": d.competitor_low_price,
            "Price Gap %": d.price_gap_pct,
            "Money Left %": d.money_left_pct,
            "Bid Value if Decided": d.bid_price.where(d.is_decided == 1),
            "Won Value": d.bid_price.where(d.is_won == 1),
            "Won Tons": d.est_tons.where(d.is_won == 1),
            "Job ID": d.job_id,
            "Job Status": d.job_status.fillna("").str.replace("_", " ").str.capitalize().replace("", None),
            "Final Revenue": d.final_revenue,
            "Actual Direct Cost": d.actual_direct_cost,
            "Actual Gross Margin %": d.actual_gross_margin_pct,
            "Margin Slip (pts)": d.margin_slip_pts,
            "Shop Hours Var %": d.shop_hours_var_pct,
            "Field Hours Var %": d.field_hours_var_pct,
            "Change Orders Requested": d.change_orders_requested,
            "Change Orders Approved": d.change_orders_approved,
            "Schedule Variance (days)": d.schedule_variance_days,
            "NCR Count": d.ncr_count,
            "Days to Final Payment": d.days_to_final_payment,
        }
    )
    return out.sort_values("Bid Date").reset_index(drop=True)


def customers(con) -> pd.DataFrame:
    c = W.df(con, "select * from analytics.mart_customer_scorecard")
    return pd.DataFrame(
        {
            "Customer ID": c.customer_id,
            "Customer": c.customer_name,
            "HQ City": c.hq_city,
            "HQ State": c.hq_state,
            "Tier": c.tier.str.title(),
            "Relationship Class": c.relationship_class,
            "Bids Submitted": c.bids_submitted,
            "Bids Decided": c.bids_decided,
            "Bids Won": c.bids_won,
            "Hit Rate": c.hit_rate_count,
            "Bid Value Decided": c.bid_value_decided,
            "Won Value": c.won_value,
            "Estimating Hours": c.estimating_hours,
            "Won $ per Est Hour": c.won_value_per_est_hour,
            "Lost on Price": c.lost_on_price,
            "Median Price Gap %": c.median_price_gap_pct,
            "Hard Bid Share": c.hard_bid_share,
            "Jobs Complete": c.jobs_complete,
            "Realised Gross Margin %": c.realized_gross_margin_pct,
            "CO Approval Rate": c.co_approval_rate,
            "Avg Days to Pay": c.avg_days_to_final_payment,
            "First Bid": pd.to_datetime(c.first_bid_date),
            "Last Bid": pd.to_datetime(c.last_bid_date),
            "Most Common Type": c.most_common_project_type.map(TYPE_LABEL),
        }
    )


def pipeline(scorecard: pd.DataFrame) -> pd.DataFrame:
    s = scorecard
    return pd.DataFrame(
        {
            "Rank": s["rank"],
            "Recommendation": s.recommendation,
            "Opportunity ID": s.opportunity_id,
            "Project": s.project_name,
            "Customer": s.customer_name,
            "Customer Tier": s.tier.str.title(),
            "Relationship Class": s.relationship_class,
            "Project Type": s.project_type_label,
            "City": s.city,
            "State": s.state,
            "Distance (mi)": s.distance_miles,
            "Tons": s.est_tons,
            "Complexity": s.complexity,
            "Delivery Method": s.delivery_method_label,
            "Scope": s.scope.map({"fab_erect": "Fab + erect", "fab_only": "Fab only"}),
            "Status": s.status.str.capitalize(),
            "Lead Source": s.lead_source,
            "Bid Due": pd.to_datetime(s.bid_due_date),
            "Fab Start Week": pd.to_datetime(s.fab_start_week),
            "Fab Weeks": s.fab_weeks,
            "GC Prior Bids": s.gc_prior_bids,
            "GC Prior Hit Rate": s.gc_prior_hit_rate,
            "Win Odds": s.p_win,
            "Expected Revenue": s.expected_revenue,
            "Expected Margin %": s.expected_margin_pct,
            "Estimating Hours": s.estimating_hours,
            "Estimating Cost": s.estimating_cost,
            "Expected Margin $": s.expected_margin_dollars,
            "Expected Value": s.expected_value,
            "EV per Est Hour": s.ev_per_est_hour,
            "EV vs Historical": s.ev_vs_historical,
            "Shop Load (backlog)": s.util_backlog,
            "Shop Load if Won": s.util_if_won,
            "Reasons": s.reasons,
        }
    )


def capacity(con) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = W.df(con, "select * from analytics.mart_capacity_weekly")
    wide = pd.DataFrame(
        {
            "Week": pd.to_datetime(c.week_start),
            "Capacity (tons)": c.capacity_tons,
            "Backlog (tons)": c.backlog_tons,
            "Weighted Pipeline (tons)": c.weighted_pipeline_tons,
            "Open Capacity (tons)": (c.capacity_tons - c.backlog_tons - c.weighted_pipeline_tons).clip(
                lower=0
            ),
            "Jobs in Shop": c.jobs_in_shop,
            "Projected Utilisation": c.projected_utilisation,
        }
    )
    long = wide.melt(
        id_vars=["Week", "Capacity (tons)"],
        value_vars=["Backlog (tons)", "Weighted Pipeline (tons)", "Open Capacity (tons)"],
        var_name="Load Type",
        value_name="Tons",
    )
    long["Load Type"] = long["Load Type"].str.replace(" (tons)", "", regex=False)
    return wide, long


def build_tables(con, scorecard: pd.DataFrame) -> dict[str, pd.DataFrame]:
    wide, long = capacity(con)
    return {
        "Bids and Jobs": bids_and_jobs(con),
        "Customers": customers(con),
        "Pipeline Scorecard": pipeline(scorecard),
        "Capacity Weekly": wide,
        "Capacity Long": long,
    }


def write(con, scorecard: pd.DataFrame, out_dir: str | Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = build_tables(con, scorecard)
    written: dict[str, Path] = {}
    xlsx = out_dir / "weibee_bid_intelligence.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl", datetime_format="yyyy-mm-dd") as xw:
        for name, frame in tables.items():
            frame.to_excel(xw, sheet_name=name, index=False)
    written["xlsx"] = xlsx
    for name, frame in tables.items():
        p = out_dir / (name.lower().replace(" ", "_") + ".csv")
        frame.to_csv(p, index=False, date_format="%Y-%m-%d")
        written[name] = p
    hyper = write_hyper(tables, out_dir / "weibee_bid_intelligence.hyper")
    if hyper:
        written["hyper"] = hyper
    return written


def write_hyper(tables: dict[str, pd.DataFrame], path: Path) -> Path | None:
    """Single-file Tableau extract with one table per sheet. Optional: needs `pip install tableauhyperapi`."""
    try:
        import tableauhyperapi as hy
    except ImportError:
        return None
    Connection, CreateMode, HyperProcess, Inserter = (
        hy.Connection,
        hy.CreateMode,
        hy.HyperProcess,
        hy.Inserter,
    )
    Nullability, SqlType, TableDefinition, TableName, Telemetry = (
        hy.Nullability,
        hy.SqlType,
        hy.TableDefinition,
        hy.TableName,
        hy.Telemetry,
    )

    def sql_type(series: pd.Series):
        if pd.api.types.is_datetime64_any_dtype(series):
            return SqlType.date()
        if pd.api.types.is_bool_dtype(series):
            return SqlType.bool()
        if pd.api.types.is_integer_dtype(series):
            return SqlType.big_int()
        if pd.api.types.is_numeric_dtype(series):
            return SqlType.double()
        return SqlType.text()

    def cell(v, series: pd.Series):
        try:
            if v is None or pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        if pd.api.types.is_datetime64_any_dtype(series):
            return pd.Timestamp(v).date()
        if pd.api.types.is_integer_dtype(series):
            return int(v)
        if pd.api.types.is_numeric_dtype(series):
            return float(v)
        return str(v)

    path.unlink(missing_ok=True)
    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
        with Connection(
            endpoint=hp.endpoint, database=str(path), create_mode=CreateMode.CREATE_AND_REPLACE
        ) as con:
            con.catalog.create_schema("Extract")
            for name, frame in tables.items():
                cols = [
                    TableDefinition.Column(c, sql_type(frame[c]), Nullability.NULLABLE) for c in frame.columns
                ]
                tdef = TableDefinition(TableName("Extract", name), cols)
                con.catalog.create_table(tdef)
                rows = [
                    [cell(v, frame[c]) for c, v in zip(frame.columns, rec, strict=True)]
                    for rec in frame.itertuples(index=False, name=None)
                ]
                with Inserter(con, tdef) as ins:
                    ins.add_rows(rows)
                    ins.execute()
    return path
