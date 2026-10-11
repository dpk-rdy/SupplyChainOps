"""Findings written from the marts, in sentences a bid meeting can act on.

Each finding is computed, not hand-written, so it stays true when the data changes. The wording is
deliberately plain: what we found, what it costs or earns, what to do about it.
"""

from __future__ import annotations

import pandas as pd

from bid_intelligence import config as C
from bid_intelligence.charts import fmt_int, fmt_money, fmt_pct


def _label(key: str) -> str:
    return C.PROJECT_TYPE_BY_KEY[key].label if key in C.PROJECT_TYPE_BY_KEY else key


def generate(ctx: dict) -> list[dict]:
    out: list[dict] = []
    dim: pd.DataFrame = ctx["hit_rate_by_dimension"]
    eva: pd.DataFrame = ctx["estimate_vs_actual"]
    cust: pd.DataFrame = ctx["customer_scorecard"]
    cap: pd.DataFrame = ctx["capacity_weekly"]
    sc: pd.DataFrame = ctx["scorecard"]
    fct: pd.DataFrame = ctx["fct_bids"]

    # 1. fit by project type: hit rate and margin slip together
    t = dim[(dim.dimension == "project_type") & (dim.bids_decided >= 8)].set_index("dimension_value")
    slip = eva[eva.dimension == "project_type"].set_index("dimension_value").margin_slip_pts
    t = t.join(slip.rename("slip")).sort_values("hit_rate_count", ascending=False)
    if len(t) >= 6:
        best, worst = t.head(3), t.tail(3)
        out.append(
            {
                "title": "Where the shop fits",
                "text": (
                    f"{', '.join(_label(k) for k in best.index)} win {fmt_pct(best.hit_rate_count.min())}-{fmt_pct(best.hit_rate_count.max())} "
                    f"of decided bids and give back {best.slip.max() * 100:.1f} pts or less of estimated margin. "
                    f"{', '.join(_label(k) for k in worst.index)} win {fmt_pct(worst.hit_rate_count.min())}-{fmt_pct(worst.hit_rate_count.max())} "
                    f"and give back {worst.slip.min() * 100:.1f}-{worst.slip.max() * 100:.1f} pts. "
                    f"Together the bottom three consumed {fmt_pct(worst.estimating_hours.sum() / t.estimating_hours.sum())} of estimating hours "
                    f"for {fmt_pct(worst.won_value.sum() / t.won_value.sum())} of dollars won."
                ),
                "action": "Default the bottom three to Review in the bid/no-bid meeting; bid them only with a relationship GC or a negotiated scope.",
            }
        )

    # 2. pricing feedback
    gap_all = fct.price_gap_pct.median()
    by_m = dim[dim.dimension == "delivery_method"].set_index("dimension_value")
    hard, neg = by_m.loc["hard_bid"], by_m.loc["negotiated"] if "negotiated" in by_m.index else None
    n_feedback = int(fct.price_gap_pct.notna().sum())
    n_price_lost = int(((fct.result == "lost") & (fct.lost_reason == "price")).sum())
    txt = (
        f"When we lose on price and get a number back ({n_feedback} of {n_price_lost} price losses), our bid is a median {fmt_pct(gap_all, 1)} above the low bid. "
        f"On hard bids the hit rate is {fmt_pct(hard.hit_rate_count)} against an average of {hard.avg_bidders:.1f} bidders"
    )
    if neg is not None:
        txt += f"; negotiated work wins {fmt_pct(neg.hit_rate_count)}."
    money_left = fct.money_left_pct.median()
    if money_left == money_left:
        txt += (
            f" When we win and learn the next number, we left a median {fmt_pct(money_left, 1)} on the table."
        )
    out.append(
        {
            "title": "Pricing feedback",
            "text": txt,
            "action": f"Collect the low number on every loss (coverage is {fmt_pct(n_feedback / max(n_price_lost, 1))} today); a gap under 3 % is a markup conversation, a gap over 10 % is a fit conversation.",
        }
    )

    # 3. price shoppers vs relationship accounts
    shoppers = cust[
        (cust.bids_decided >= 6) & (cust.median_price_gap_pct >= 0.09) & (cust.hit_rate_count <= 0.25)
    ]
    a_class = cust[cust.relationship_class == "A"]
    if len(shoppers):
        hours = shoppers.estimating_hours.sum()
        out.append(
            {
                "title": "Price shoppers",
                "text": (
                    f"{len(shoppers)} general contractors ({', '.join(shoppers.customer_name.head(4))}{'…' if len(shoppers) > 4 else ''}) "
                    f"have awarded us {fmt_pct(shoppers.hit_rate_count.mean())} of bids with a median price gap of {fmt_pct(shoppers.median_price_gap_pct.median(), 1)}: "
                    f"{fmt_int(hours)} estimating hours for {fmt_money(shoppers.won_value.sum())} won. "
                    f"The {len(a_class)} A-class accounts returned {fmt_money(a_class.won_value.sum())} on {fmt_int(a_class.estimating_hours.sum())} hours."
                ),
                "action": "Bid price-shopper invitations only when the shop needs fill-in work; spend the hours on A-class GCs and on new accounts that look like them.",
            }
        )

    # 4. distance
    d = dim[dim.dimension == "distance_band"].set_index("dimension_value")
    fv = eva[eva.dimension == "distance_band"].set_index("dimension_value").field_hours_var_pct
    if "< 60 mi" in d.index and "250 mi +" in d.index:
        far_fv = fv.get("250 mi +", float("nan"))
        out.append(
            {
                "title": "Geography",
                "text": (
                    f"Hit rate falls from {fmt_pct(d.loc['< 60 mi'].hit_rate_count)} inside 60 miles to {fmt_pct(d.loc['250 mi +'].hit_rate_count)} beyond 250 "
                    f"({int(d.loc['250 mi +'].bids_decided)} bids)."
                    + (
                        f" Field hours on far jobs ran {fmt_pct(far_fv)} over estimate."
                        if far_fv == far_fv
                        else ""
                    )
                ),
                "action": f"Treat erection work beyond {C.FAR_JOB_MILES:.0f} miles as fab-only unless the GC is a relationship account; price per-diem crews explicitly when we do erect.",
            }
        )

    # 5. capacity and pipeline coverage
    today = ctx["snapshot_date"]
    nxt = cap[(cap.week_start >= today) & (cap.week_start < today + pd.Timedelta(weeks=52))]
    backlog_tons = cap[cap.week_start >= today].backlog_tons.sum()
    weeks_cover = backlog_tons / C.SHOP_CAPACITY_TONS_PER_WEEK
    q = (
        nxt.assign(q=nxt.week_start.dt.to_period("Q").astype(str))
        .groupby("q")
        .agg(
            u=("projected_utilisation", "mean"),
            b=("backlog_tons", "mean"),
            w=("weighted_pipeline_tons", "mean"),
        )
    )
    low = q[q.u < 0.7]
    pursue = sc[sc.recommendation == "Pursue"]
    out.append(
        {
            "title": "Capacity and pipeline coverage",
            "text": (
                f"Won work still to fabricate is {fmt_int(backlog_tons)} tons, {weeks_cover:.0f} weeks at {C.SHOP_CAPACITY_TONS_PER_WEEK:.0f} tons/week. "
                f"Adding the probability-weighted pipeline, projected utilisation over the next four quarters is "
                + ", ".join(f"{k} {fmt_pct(v)}" for k, v in q.u.items())
                + (f". {len(low)} of those quarters sit below 70 %." if len(low) else ".")
            ),
            "action": (
                f"The {len(pursue)} Pursue opportunities carry {fmt_int(pursue.est_tons.sum())} tons at {fmt_pct(pursue.p_win.mean())} average win odds; "
                f"to fill the open quarters the pipeline needs roughly {fmt_int(max(0.0, (0.85 - q.u.mean()) * C.SHOP_CAPACITY_TONS_PER_WEEK * 52 / max(sc.p_win.mean(), 0.05)))} more tons of identified opportunities at today's hit rate."
            ),
        }
    )

    # 6. estimate vs actual overall
    allj = eva[eva.dimension == "all"].iloc[0]
    worst_cx = eva[eva.dimension == "complexity"].sort_values("margin_slip_pts", ascending=False).iloc[0]
    out.append(
        {
            "title": "Estimated versus actual",
            "text": (
                f"Across {int(allj.jobs_complete)} completed jobs we estimated {fmt_pct(allj.est_gross_margin_pct, 1)} gross margin and realised {fmt_pct(allj.actual_gross_margin_pct, 1)}: "
                f"{allj.margin_slip_pts * 100:.1f} pts, about {fmt_money(allj.margin_slip_pts * allj.revenue)} of margin. Shop hours ran {fmt_pct(allj.shop_hours_var_pct)} over estimate and field hours {fmt_pct(allj.field_hours_var_pct)}; "
                f"{worst_cx.dimension_value} work slipped most ({worst_cx.margin_slip_pts * 100:.1f} pts)."
            ),
            "action": "Feed realised margin by project type and complexity back into the estimate as a line-item contingency instead of a flat markup.",
        }
    )

    # 7. model honesty
    diag = ctx["model_diagnostics"]["test"]
    out.append(
        {
            "title": "How much to trust the win odds",
            "text": (
                f"Out-of-time test on {diag['n']} bids after {ctx['model_diagnostics']['cutoff']}: AUC {diag['auc']:.2f}, Brier {diag['brier']:.3f} against {diag['brier_baseline']:.3f} for always guessing the base rate. "
                "The model separates good bets from bad ones; it does not call individual bids. Use it to rank and to budget estimating hours, not to skip a job the room believes in."
            ),
            "action": "Re-fit quarterly; the model gets better with every decided bid and every low-bid number we collect.",
        }
    )
    return out
