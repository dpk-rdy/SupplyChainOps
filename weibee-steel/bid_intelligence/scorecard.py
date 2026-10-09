"""Bid / no-bid scorecard for the forward pipeline.

For every upcoming opportunity the scorecard answers four questions an estimating manager asks before
spending a week on a takeoff:

1. **Can we win it?**   win probability from the logistic model, using the customer's history with us.
2. **Is it worth it?**  expected gross margin dollars = P(win) x revenue x the margin we *actually*
   realise on that kind of work, minus the cost of estimating it. Ranked per estimating hour, because
   estimating hours are the scarce resource.
3. **Can we build it?** projected shop utilisation over the fabrication window if we win it, from the
   backlog plus the probability-weighted rest of the pipeline.
4. **Anything else?**   distance, new-customer, strategic-account flags.

The recommendation (Pursue / Review / Pass) is a starting point for the weekly bid meeting, not a
verdict. Every input is shown next to it so the room can argue with the number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bid_intelligence import config as C
from bid_intelligence import win_model as M

MARGIN_SHRINK_JOBS = 5.0  # pseudo-jobs pulling a project type's realised margin toward the overall figure


# ------------------------------------------------------------------ fitted business inputs
def fit_estimating_effort(fct_bids: pd.DataFrame) -> dict[str, float]:
    """log(hours) = a + b*log(tons) + c*complexity, fitted on our own bid history."""
    b = fct_bids.dropna(subset=["estimating_hours"])
    x = np.column_stack([np.ones(len(b)), np.log(b.est_tons.to_numpy(float)), b.complexity.to_numpy(float)])
    y = np.log(b.estimating_hours.to_numpy(float))
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ coef
    return {
        "a": float(coef[0]),
        "b_log_tons": float(coef[1]),
        "c_complexity": float(coef[2]),
        "rmse_log": float(resid.std()),
    }


def predict_estimating_hours(tons: np.ndarray, complexity: np.ndarray, fit: dict[str, float]) -> np.ndarray:
    return np.exp(fit["a"] + fit["b_log_tons"] * np.log(tons) + fit["c_complexity"] * complexity)


def historical_margin_per_est_hour(fct_bids: pd.DataFrame, years: float = 2.0) -> float:
    """Gross-margin dollars won per estimating hour spent, trailing window. The yardstick for EV."""
    cutoff = fct_bids.bid_date.max() - pd.Timedelta(days=int(365 * years))
    w = fct_bids[(fct_bids.bid_date >= cutoff) & (fct_bids.result != "pending")]
    margin_won = float((w.bid_price * w.est_gross_margin_pct * w.is_won).sum())
    hours = float(w.estimating_hours.sum())
    return margin_won / hours if hours else 0.0


def price_per_ton_by_type(fct_bids: pd.DataFrame) -> pd.Series:
    return fct_bids[fct_bids.is_decided == 1].groupby("project_type").price_per_ton.median()


def expected_margin_by_type(est_vs_actual: pd.DataFrame) -> tuple[pd.Series, float]:
    """Realised gross margin by project type, shrunk toward the overall figure for thin history."""
    overall_row = est_vs_actual[(est_vs_actual.dimension == "all")]
    overall = float(overall_row.actual_gross_margin_pct.iloc[0]) if len(overall_row) else 0.18
    t = est_vs_actual[est_vs_actual.dimension == "project_type"].set_index("dimension_value")
    shrunk = (t.actual_gross_margin_pct * t.jobs_complete + overall * MARGIN_SHRINK_JOBS) / (
        t.jobs_complete + MARGIN_SHRINK_JOBS
    )
    return shrunk, overall


# ------------------------------------------------------------------ scoring
def _window_utilisation(
    backlog: pd.DataFrame, start: pd.Timestamp, weeks: int, extra: pd.Series | None = None
) -> float:
    end = start + pd.Timedelta(weeks=weeks)
    w = backlog[(backlog.week_start >= start) & (backlog.week_start < end)]
    if w.empty:
        return float("nan")
    load = w.backlog_tons.to_numpy(float)
    if extra is not None:
        load = load + extra.reindex(w.week_start).fillna(0).to_numpy(float)
    return float((load / w.capacity_tons.to_numpy(float)).mean())


def score_pipeline(
    pipeline: pd.DataFrame,
    fct_bids: pd.DataFrame,
    customers: pd.DataFrame,
    customer_scorecard: pd.DataFrame,
    est_vs_actual: pd.DataFrame,
    backlog: pd.DataFrame,
    model: M.LogisticModel,
) -> pd.DataFrame:
    base_rate = float(fct_bids[fct_bids.is_decided == 1].is_won.mean())
    hist = M.customer_history_as_of(fct_bids, base_rate)
    effort = fit_estimating_effort(fct_bids)
    ppt = price_per_ton_by_type(fct_bids)
    margin_by_type, overall_margin = expected_margin_by_type(est_vs_actual)
    type_hit = (
        fct_bids[fct_bids.is_decided == 1].groupby("project_type").is_won.mean().sort_values(ascending=False)
    )
    best_fit_types = set(type_hit.head(3).index)
    yardstick = historical_margin_per_est_hour(fct_bids)

    p = pipeline.copy()
    p = p.merge(customers[["customer_id", "customer_name", "tier"]], on="customer_id", how="left")
    p = p.merge(customer_scorecard[["customer_id", "relationship_class"]], on="customer_id", how="left")
    p = p.merge(hist, left_on="customer_id", right_index=True, how="left")
    p["gc_prior_bids"] = p["gc_prior_bids"].fillna(0.0)
    p["gc_prior_hit_rate"] = p["gc_prior_hit_rate"].fillna(base_rate)
    p["relationship_class"] = p["relationship_class"].fillna("New / thin")
    p["markup_pct"] = C.TARGET_MARKUP_PCT
    p["num_bidders"] = p["delivery_method"].map(lambda m: C.DELIVERY_METHODS[m][1]).round()

    x, _ = M.design_matrix(p)
    p["p_win"] = model.predict_proba(x)

    p["price_per_ton"] = p["project_type"].map(ppt).fillna(ppt.median())
    p["expected_revenue"] = p["est_tons"] * p["price_per_ton"]
    p["expected_margin_pct"] = p["project_type"].map(margin_by_type).fillna(overall_margin)
    p["estimating_hours"] = predict_estimating_hours(
        p.est_tons.to_numpy(float), p.complexity.to_numpy(float), effort
    ).round(1)
    p["estimating_cost"] = p["estimating_hours"] * C.ESTIMATOR_RATE_PER_HOUR
    p["expected_margin_dollars"] = p["p_win"] * p["expected_revenue"] * p["expected_margin_pct"]
    p["expected_value"] = p["expected_margin_dollars"] - p["estimating_cost"]
    p["ev_per_est_hour"] = p["expected_value"] / p["estimating_hours"]

    # capacity: backlog plus the probability-weighted load of *other* pipeline work, then this job in full
    weeks = backlog.week_start
    weighted = pd.Series(0.0, index=weeks)
    per_job: dict[str, pd.Series] = {}
    for _, r in p.iterrows():
        mask = (weeks >= r.fab_start_week) & (weeks < r.fab_start_week + pd.Timedelta(weeks=int(r.fab_weeks)))
        s = pd.Series(np.where(mask, r.est_tons / r.fab_weeks, 0.0), index=weeks)
        per_job[r.opportunity_id] = s
        weighted = weighted + r.p_win * s
    util_backlog, util_if_won = [], []
    for _, r in p.iterrows():
        own = per_job[r.opportunity_id]
        others = weighted - r.p_win * own
        util_backlog.append(_window_utilisation(backlog, r.fab_start_week, int(r.fab_weeks)))
        util_if_won.append(
            _window_utilisation(backlog, r.fab_start_week, int(r.fab_weeks), extra=others + own)
        )
    p["util_backlog"] = util_backlog
    p["util_if_won"] = util_if_won

    recs, reasons = [], []
    for _, r in p.iterrows():
        rec, why = recommend(r, best_fit_types, overall_margin, yardstick)
        recs.append(rec)
        reasons.append(why)
    p["recommendation"] = recs
    p["reasons"] = reasons
    p["project_type_label"] = p["project_type"].map(lambda k: C.PROJECT_TYPE_BY_KEY[k].label)
    p["delivery_method_label"] = p["delivery_method"].map(lambda k: C.DELIVERY_METHODS[k][0])
    p["ev_vs_historical"] = p["ev_per_est_hour"] / yardstick if yardstick else float("nan")
    p["rank"] = p["ev_per_est_hour"].rank(ascending=False, method="first").astype(int)
    cols = [
        "rank",
        "opportunity_id",
        "project_name",
        "customer_id",
        "customer_name",
        "tier",
        "relationship_class",
        "project_type",
        "project_type_label",
        "city",
        "state",
        "distance_miles",
        "est_tons",
        "complexity",
        "delivery_method",
        "delivery_method_label",
        "scope",
        "status",
        "lead_source",
        "bid_due_date",
        "fab_start_week",
        "fab_weeks",
        "gc_prior_bids",
        "gc_prior_hit_rate",
        "p_win",
        "price_per_ton",
        "expected_revenue",
        "expected_margin_pct",
        "estimating_hours",
        "estimating_cost",
        "expected_margin_dollars",
        "expected_value",
        "ev_per_est_hour",
        "ev_vs_historical",
        "util_backlog",
        "util_if_won",
        "recommendation",
        "reasons",
    ]
    return p[cols].sort_values("rank").reset_index(drop=True)


def recommend(
    r: pd.Series, best_fit_types: set[str], overall_margin: float, yardstick: float
) -> tuple[str, str]:
    pursue_floor = C.PURSUE_EV_RATIO * yardstick
    review_floor = C.REVIEW_EV_RATIO * yardstick
    hard: list[str] = []
    soft: list[str] = []
    plus: list[str] = []
    if r.util_if_won > C.CAPACITY_OVER_UTILISATION:
        hard.append(f"shop at {r.util_if_won:.0%} of capacity if won")
    elif r.util_if_won > C.CAPACITY_TIGHT_UTILISATION:
        soft.append(f"shop tight ({r.util_if_won:.0%}) during fabrication window")
    if r.p_win < C.MIN_WIN_PROBABILITY:
        hard.append(f"win odds {r.p_win:.0%}")
    if r.distance_miles > C.FAR_JOB_MILES and r.scope == "fab_erect":
        soft.append(f"erection {r.distance_miles:.0f} mi out (per-diem crew)")
    if r.expected_margin_pct < overall_margin - 0.04:
        soft.append(
            f"we realise only {r.expected_margin_pct:.0%} margin on {C.PROJECT_TYPE_BY_KEY[r.project_type].label.lower()} work"
        )
    if r.gc_prior_bids == 0:
        soft.append("no bid history with this GC")
    if r.gc_prior_hit_rate >= 0.40 and r.gc_prior_bids >= 4:
        plus.append(f"relationship GC ({r.gc_prior_hit_rate:.0%} hit rate, {int(r.gc_prior_bids)} bids)")
    if r.project_type in best_fit_types:
        plus.append("project type we win and execute well")
    if r.delivery_method in ("negotiated", "design_build"):
        plus.append(f"{r.delivery_method.replace('_', '-')} delivery")

    strategic = (
        r.gc_prior_bids == 0 and r.tier in ("regional", "national") and r.project_type in best_fit_types
    )
    if hard:
        rec = "Pass"
    elif r.expected_value <= 0:
        rec = "Pass"
    elif r.ev_per_est_hour >= pursue_floor and not soft:
        rec = "Pursue"
    elif r.ev_per_est_hour >= pursue_floor:
        rec = "Pursue" if len(soft) == 1 and soft[0].startswith("no bid history") else "Review"
    elif r.ev_per_est_hour >= review_floor:
        rec = "Review"
    else:
        rec = "Pass"
        soft.append(
            f"EV per estimating hour only {r.ev_per_est_hour / yardstick:.0%} of our historical return"
            if yardstick
            else "low EV"
        )
    if rec == "Pass" and strategic and r.p_win >= C.MIN_WIN_PROBABILITY and not hard:
        rec = "Review"
        plus.append("strategic: new regional/national GC on best-fit work")
    why = "; ".join(hard + soft + plus) or "no flags"
    return rec, why
