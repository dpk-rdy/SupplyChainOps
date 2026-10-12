"""Render the bid-intelligence report as one self-contained HTML file."""

from __future__ import annotations

import html
from datetime import datetime

import pandas as pd

from bid_intelligence import charts as ch
from bid_intelligence import config as C

REC_CLASS = {"Pursue": "good", "Review": "warn", "Pass": "muted"}


def _e(s: object) -> str:
    return html.escape("" if s is None else str(s))


def _label(key: str) -> str:
    return C.PROJECT_TYPE_BY_KEY[key].label if key in C.PROJECT_TYPE_BY_KEY else str(key)


def _method(key: str) -> str:
    return C.DELIVERY_METHODS[key][0] if key in C.DELIVERY_METHODS else str(key)


def table(df: pd.DataFrame, cols: list[tuple[str, str, object]], cls: str = "") -> str:
    """cols: (column, header, formatter)."""
    head = "".join(f"<th>{_e(h)}</th>" for _, h, _ in cols)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c, _, f in cols:
            v = r[c]
            cells.append(f"<td>{f(v) if f else _e(v)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table class='{cls}'><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def tile(label: str, value: str, note: str = "") -> str:
    return f"<div class='tile'><div class='tile-v'>{_e(value)}</div><div class='tile-l'>{_e(label)}</div><div class='tile-n'>{_e(note)}</div></div>"


def section(id_: str, title: str, lede: str, body: str) -> str:
    return f"<section id='{id_}'><h2>{_e(title)}</h2><p class='lede'>{lede}</p>{body}</section>"


def card(title: str, body: str, foot: str = "") -> str:
    return f"<div class='card'><h3>{_e(title)}</h3>{body}{f'<p class=foot>{foot}</p>' if foot else ''}</div>"


# ------------------------------------------------------------------ sections
def headline_tiles(ctx: dict) -> str:
    f = ctx["fct_bids"]
    today = ctx["snapshot_date"]
    ttm = f[(f.bid_date > today - pd.Timedelta(days=365)) & (f.is_decided == 1)]
    prior = f[
        (f.bid_date > today - pd.Timedelta(days=730))
        & (f.bid_date <= today - pd.Timedelta(days=365))
        & (f.is_decided == 1)
    ]
    hr, hr_prev = ttm.is_won.mean(), prior.is_won.mean()
    won = ttm[ttm.is_won == 1].bid_price.sum()
    cap = ctx["capacity_weekly"]
    backlog_tons = cap[cap.week_start >= today].backlog_tons.sum()
    eva = ctx["estimate_vs_actual"]
    allj = eva[eva.dimension == "all"].iloc[0]
    sc = ctx["scorecard"]
    pursue = sc[sc.recommendation == "Pursue"]
    nxt = cap[(cap.week_start >= today) & (cap.week_start < today + pd.Timedelta(weeks=52))]
    return (
        "<div class='tiles'>"
        + "".join(
            [
                tile(
                    "Hit rate, trailing 12 months",
                    ch.fmt_pct(hr),
                    f"{int(ttm.is_won.sum())} of {len(ttm)} decided bids; prior year {ch.fmt_pct(hr_prev)}",
                ),
                tile(
                    "Value won, trailing 12 months",
                    ch.fmt_money(won),
                    f"{ch.fmt_int(ttm[ttm.is_won == 1].est_tons.sum())} tons",
                ),
                tile(
                    "Won work waiting for the shop",
                    f"{backlog_tons / C.SHOP_CAPACITY_TONS_PER_WEEK:.0f} weeks",
                    f"{ch.fmt_int(backlog_tons)} tons at {C.SHOP_CAPACITY_TONS_PER_WEEK:.0f} tons a week",
                ),
                tile(
                    "How full the shop looks, next 12 months",
                    ch.fmt_pct(nxt.projected_utilisation.mean()),
                    "won work plus upcoming work counted at its win odds",
                ),
                tile(
                    "Margin we estimated but did not keep",
                    f"{allj.margin_slip_pts * 100:.1f} pts",
                    f"estimated {ch.fmt_pct(allj.est_gross_margin_pct, 1)}, actually earned {ch.fmt_pct(allj.actual_gross_margin_pct, 1)}",
                ),
                tile(
                    "Upcoming projects worth chasing",
                    f"{len(pursue)} of {len(sc)}",
                    f"about {ch.fmt_int(pursue.estimating_hours.sum())} estimating hours to bid them all",
                ),
            ]
        )
        + "</div>"
    )


def findings(ctx: dict) -> str:
    items = "".join(
        f"<li><b>{_e(i['title'])}.</b> {_e(i['text'])} <span class='action'>→ {_e(i['action'])}</span></li>"
        for i in ctx["insights"]
    )
    return f"<ol class='findings'>{items}</ol>"


def hit_rate_section(ctx: dict) -> str:
    dim = ctx["hit_rate_by_dimension"]
    q = ctx["quarterly"]
    labels = [f"{d.year} Q{(d.month - 1) // 3 + 1}" for d in q.bid_quarter]
    tips = [
        f"{lab}: {int(r.bids_won)} of {int(r.bids_decided)} decided bids ({ch.fmt_pct(r.hit_rate_count)}); by value {ch.fmt_pct(r.hit_rate_value)}; {ch.fmt_money(r.won_value)} won"
        for lab, (_, r) in zip(labels, q.iterrows(), strict=True)
    ]
    trend = ch.line_chart(
        labels,
        [
            ("Hit rate by count", ch.BLUE, q.hit_rate_count.tolist()),
            ("Hit rate by value", ch.ORANGE, q.hit_rate_value.tolist()),
        ],
        y_max=0.7,
        tooltips=tips,
    )

    def rows_for(dimension: str, labeler=lambda v: v, order: list[str] | None = None) -> list[dict]:
        d = dim[dim.dimension == dimension].copy()
        if order:
            d["o"] = d.dimension_value.map({v: i for i, v in enumerate(order)})
            d = d.sort_values("o")
        else:
            d = d.sort_values("hit_rate_count", ascending=False)
        return [
            {
                "label": labeler(r.dimension_value),
                "value": r.hit_rate_count,
                "note": f"{int(r.bids_won)}/{int(r.bids_decided)}",
                "tooltip": f"{labeler(r.dimension_value)}: {ch.fmt_pct(r.hit_rate_count)} by count, {ch.fmt_pct(r.hit_rate_value)} by value; {ch.fmt_money(r.won_value)} won on {ch.fmt_int(r.estimating_hours)} estimating hours ({ch.fmt_money(r.won_value_per_est_hour)}/hr)",
            }
            for _, r in d.iterrows()
        ]

    overall = ctx["fct_bids"][ctx["fct_bids"].is_decided == 1].is_won.mean()
    by_type = ch.hbar(
        rows_for("project_type", _label),
        max_value=0.7,
        reference=overall,
        reference_label=f"all {ch.fmt_pct(overall)}",
    )
    by_size = ch.hbar(
        rows_for("size_band", order=[b[2] for b in C.SIZE_BANDS]),
        max_value=0.7,
        reference=overall,
        reference_label="all",
    )
    by_dist = ch.hbar(
        rows_for("distance_band", order=[b[2] for b in C.DISTANCE_BANDS]),
        max_value=0.7,
        reference=overall,
        reference_label="all",
    )
    by_method = ch.hbar(
        rows_for("delivery_method", _method), max_value=0.7, reference=overall, reference_label="all"
    )
    eff = dim[dim.dimension == "project_type"].sort_values("won_value_per_est_hour", ascending=False)
    eff_rows = [
        {
            "label": _label(r.dimension_value),
            "value": r.won_value_per_est_hour,
            "note": f"{ch.fmt_int(r.estimating_hours)} h",
            "color": ch.GREEN,
        }
        for _, r in eff.iterrows()
    ]
    by_eff = ch.hbar(eff_rows, value_fmt=ch.fmt_money, color=ch.GREEN)
    grid = (
        "<div class='grid2'>"
        + card(
            "Hit rate by quarter",
            trend,
            "Count and dollar hit rates on decided bids (won + lost). Cancelled projects are excluded.",
        )
        + card("By project type", by_type)
        + card("By size", by_size)
        + card("By distance from the shop", by_dist)
        + card("By delivery method", by_method)
        + card(
            "Dollars won per estimating hour, by project type",
            by_eff,
            "Estimating hours are the scarce input; this is the return on them.",
        )
        + "</div>"
    )
    return grid


def customers_section(ctx: dict) -> str:
    c = ctx["customer_scorecard"].copy()
    c = c[c.bids_decided.fillna(0) > 0].sort_values("won_value", ascending=False)
    cols = [
        ("customer_name", "General contractor", None),
        ("tier", "Tier", None),
        ("relationship_class", "Class", lambda v: f"<span class='badge cls-{_e(v)[:1]}'>{_e(v)}</span>"),
        ("bids_decided", "Bids", ch.fmt_int),
        ("hit_rate_count", "Hit rate", ch.fmt_pct),
        ("won_value", "Won", ch.fmt_money),
        ("won_value_per_est_hour", "Won / est. hr", ch.fmt_money),
        ("median_price_gap_pct", "Median price gap", lambda v: ch.fmt_pct(v, 1)),
        ("realized_gross_margin_pct", "Realised margin", ch.fmt_pct),
        ("co_approval_rate", "CO approval", ch.fmt_pct),
        ("avg_days_to_final_payment", "Days to pay", ch.fmt_int),
        ("most_common_project_type", "Mostly", _label),
    ]
    return card(
        "Customer scorecard",
        table(c, cols, cls="dense"),
        "A = awards us ≥ 40 % and executes at or above shop margin; B = awards ≥ 22 %; C = below. Sorted by value won. The class is a starting point for account planning, not a verdict.",
    )


def execution_section(ctx: dict) -> str:
    eva = ctx["estimate_vs_actual"]
    t = eva[eva.dimension == "project_type"].sort_values("margin_slip_pts", ascending=False)
    rows = [
        {
            "label": _label(r.dimension_value),
            "a": r.est_gross_margin_pct,
            "b": r.actual_gross_margin_pct,
            "note": f"n={int(r.jobs_complete)}",
        }
        for _, r in t.iterrows()
    ]
    lo = min(0.05, min(r["b"] for r in rows) - 0.02) if rows else 0
    hi = max(0.30, max(r["a"] for r in rows) + 0.03) if rows else 0.3
    by_type = ch.dumbbell(rows, lo, hi)
    cx = eva[eva.dimension == "complexity"].sort_values("dimension_value")
    cx_rows = [
        {
            "label": r.dimension_value.replace("complexity", "Complexity"),
            "a": r.est_gross_margin_pct,
            "b": r.actual_gross_margin_pct,
            "note": f"n={int(r.jobs_complete)}",
        }
        for _, r in cx.iterrows()
    ]
    by_cx = ch.dumbbell(cx_rows, lo, hi)
    hours = eva[eva.dimension.isin(["project_type"])].sort_values("field_hours_var_pct", ascending=False)
    hrows = [
        {
            "label": _label(r.dimension_value),
            "value": max(r.field_hours_var_pct, 0),
            "note": f"shop {ch.fmt_pct(r.shop_hours_var_pct)}",
            "color": ch.ORANGE,
            "tooltip": f"{_label(r.dimension_value)}: field hours {ch.fmt_pct(r.field_hours_var_pct)} vs estimate, shop hours {ch.fmt_pct(r.shop_hours_var_pct)}, schedule {r.avg_schedule_variance_days:+.0f} days",
        }
        for _, r in hours.iterrows()
    ]
    by_hours = ch.hbar(hrows, color=ch.ORANGE)
    return (
        "<div class='grid2'>"
        + card(
            "Estimated vs realised gross margin, by project type",
            by_type,
            "Dollar-weighted over completed jobs. Gross margin is before overhead.",
        )
        + card(
            "By complexity", by_cx, "1 = simple braced frames, 5 = AESS, long span, heavy moment connections."
        )
        + card(
            "Field-hour overrun by project type",
            by_hours,
            "Positive = more hours than estimated. Shop variance in the note.",
        )
        + "</div>"
    )


def pricing_section(ctx: dict) -> str:
    pf = ctx["pricing_feedback"]
    order = ["0-2 %", "2-4 %", "4-6 %", "6-8 %", "8-10 %", "10-15 %", "15 % +"]
    agg = pf.groupby("gap_bucket").bids_lost_on_price.sum().reindex(order).fillna(0)
    hist = ch.vbar(order, agg.tolist(), color=ch.PURPLE)
    by_m = pf.groupby("delivery_method").bids_lost_on_price.sum()
    f = ctx["fct_bids"]
    med = f.groupby("delivery_method").price_gap_pct.median()
    rows = [
        {
            "label": _method(m),
            "value": med.get(m, float("nan")),
            "note": f"n={int(by_m.get(m, 0))}",
            "color": ch.PURPLE,
        }
        for m in C.DELIVERY_METHODS
        if m in med.index and med[m] == med[m]
    ]
    by_method = ch.hbar(rows, value_fmt=lambda v: ch.fmt_pct(v, 1), color=ch.PURPLE, max_value=0.15)
    return (
        "<div class='grid2'>"
        + card(
            "How far above the low bid were we when we lost on price?",
            hist,
            "Lost-on-price bids where the GC shared the low number.",
        )
        + card("Median price gap by delivery method", by_method)
        + "</div>"
    )


def capacity_section(ctx: dict) -> str:
    cap = ctx["capacity_weekly"]
    today = ctx["snapshot_date"]
    w = cap[
        (cap.week_start >= today - pd.Timedelta(weeks=26)) & (cap.week_start < today + pd.Timedelta(weeks=78))
    ].reset_index(drop=True)
    labels = [d.strftime("%b %y") for d in w.week_start]
    today_idx = int((w.week_start >= today).idxmax())
    chart = ch.stacked_area(
        labels,
        [
            ("Backlog (won)", ch.BLUE, w.backlog_tons.tolist()),
            ("Pipeline × win odds", ch.AMBER, w.weighted_pipeline_tons.tolist()),
        ],
        line=("Shop capacity", "#0b0b0b", w.capacity_tons.tolist()),
        y_fmt=lambda v: f"{v:,.0f} t",
        today_index=today_idx,
    )
    q = (
        w[w.week_start >= today]
        .assign(q=lambda d: d.week_start.dt.to_period("Q").astype(str))
        .groupby("q")
        .agg(
            backlog=("backlog_tons", "mean"),
            pipeline=("weighted_pipeline_tons", "mean"),
            util=("projected_utilisation", "mean"),
        )
        .reset_index()
    )
    tbl = table(
        q,
        [
            ("q", "Quarter", None),
            ("backlog", "Backlog t/wk", ch.fmt_int),
            ("pipeline", "Weighted pipeline t/wk", ch.fmt_int),
            ("util", "Projected utilisation", ch.fmt_pct),
        ],
    )
    return (
        "<div class='grid2'>"
        + card(
            "Shop load: backlog and probability-weighted pipeline vs capacity, tons per week",
            chart,
            "Each won job spreads its tonnage evenly over its fabrication window; each pipeline opportunity contributes tons × win probability over its expected window.",
        )
        + card("By quarter", tbl)
        + "</div>"
    )


def scorecard_section(ctx: dict, top_n: int | None = None) -> str:
    sc = ctx["scorecard"]
    ranked = sc.head(top_n) if top_n else sc
    cols = [
        ("rank", "#", ch.fmt_int),
        (
            "recommendation",
            "Call",
            lambda v: f"<span class='badge rec-{REC_CLASS.get(v, 'muted')}'>{_e(v)}</span>",
        ),
        ("project_name", "Project", None),
        ("customer_name", "GC", lambda v: _e(v)),
        ("project_type", "Type", _label),
        ("est_tons", "Tons", ch.fmt_int),
        ("distance_miles", "Miles", ch.fmt_int),
        ("delivery_method", "Delivery", _method),
        ("p_win", "Win odds", ch.fmt_pct),
        ("ev_per_est_hour", "EV / est. hr", ch.fmt_money),
        ("util_if_won", "Shop load if won", ch.fmt_pct),
        ("reasons", "Why", lambda v: f"<span class='why'>{_e(v)}</span>"),
        ("relationship_class", "Class", None),
        ("city", "City", None),
        ("complexity", "Cx", ch.fmt_int),
        ("bid_due_date", "Bid due", lambda v: pd.Timestamp(v).strftime("%b %Y")),
        ("expected_revenue", "Revenue", ch.fmt_money),
        ("expected_margin_pct", "Exp. margin", ch.fmt_pct),
        ("estimating_hours", "Est. hrs", lambda v: f"{v:.0f}"),
        ("expected_value", "EV", ch.fmt_money),
    ]
    summary = (
        sc.groupby("recommendation")
        .agg(
            n=("rank", "size"),
            hours=("estimating_hours", "sum"),
            ev=("expected_value", "sum"),
            tons=("est_tons", "sum"),
        )
        .reindex(["Pursue", "Review", "Pass"])
        .fillna(0)
        .reset_index()
    )
    stbl = table(
        summary,
        [
            ("recommendation", "Call", None),
            ("n", "Opportunities", ch.fmt_int),
            ("hours", "Estimating hours", ch.fmt_int),
            ("tons", "Tons", ch.fmt_int),
            ("ev", "Expected margin $ net of estimating", ch.fmt_money),
        ],
    )
    return card("Summary", stbl) + card(
        f"Ranked opportunities (next 6-24 months{f', top {top_n} of {len(sc)}' if top_n else ''})",
        table(ranked, cols, cls="dense scorecard"),
        "EV = win odds × expected revenue × margin we actually realise on that project type, minus estimating cost. EV per estimating hour is ranked against what an hour has returned historically (Pursue ≥ 80 %, Review ≥ 35 %). Shop load = backlog + the rest of the pipeline weighted by its odds + this job in full, averaged over its fabrication window.",
    )


def model_section(ctx: dict) -> str:
    d = ctx["model_diagnostics"]
    coefs = ctx["model_coefficients"].head(12)
    rows = [
        {
            "label": r.feature.replace("type=", "type: ").replace("method=", "method: "),
            "value": abs(r.coef_std),
            "note": "raises odds" if r.coef_std > 0 else "lowers odds",
            "color": ch.GREEN if r.coef_std > 0 else ch.ORANGE,
            "tooltip": f"{r.feature}: {r.coef_std:+.2f} log-odds per standard deviation",
        }
        for _, r in coefs.iterrows()
    ]
    coef_chart = ch.hbar(rows, value_fmt=lambda v: f"{v:.2f}", max_value=max(r["value"] for r in rows) * 1.3)
    cal = ch.calibration(d["test"]["calibration"])
    metrics = pd.DataFrame(
        [{"split": k, **{m: v for m, v in d[k].items() if m != "calibration"}} for k in ("train", "test")]
    )
    mtbl = table(
        metrics,
        [
            ("split", "Split", None),
            ("n", "Bids", ch.fmt_int),
            ("base_rate", "Base rate", ch.fmt_pct),
            ("auc", "AUC", lambda v: f"{v:.2f}"),
            ("brier", "Brier", lambda v: f"{v:.3f}"),
            ("brier_baseline", "Brier, base-rate guess", lambda v: f"{v:.3f}"),
            ("log_loss", "Log loss", lambda v: f"{v:.3f}"),
            ("log_loss_baseline", "Log loss, base-rate guess", lambda v: f"{v:.3f}"),
        ],
    )
    return (
        "<div class='grid2'>"
        + card(
            "What moves the win odds",
            coef_chart,
            "Standardised logistic-regression coefficients; reference levels are warehouse work and hard bid. Green raises the odds, orange lowers them.",
        )
        + card(
            "Calibration on held-out bids",
            cal + mtbl,
            f"Trained on bids before {d['cutoff']}, tested on the ones after. Points near the diagonal mean a 30 % call wins about 30 % of the time.",
        )
        + "</div>"
    )


def glossary() -> str:
    terms = [
        (
            "Hit rate",
            "Share of decided bids we won. By count: 3 wins out of 10 bids is 30 %. By value: dollars won divided by dollars bid, which tells you whether we win the big ones or the small ones.",
        ),
        (
            "Decided bid",
            "A bid that was won or lost. Cancelled projects and bids still waiting on an answer are left out so they do not drag the hit rate down.",
        ),
        (
            "Gross margin",
            "What is left of the contract price after material, shop labour and field labour. Before overhead and profit. 'Estimated' is what the bid assumed; 'realised' is what the job actually earned.",
        ),
        (
            "Margin slip",
            "Estimated gross margin minus realised gross margin, in percentage points. 5 pts of slip on a $1M job is $50,000 that was in the estimate and not in the bank.",
        ),
        (
            "Price gap",
            "When we lose on price and the GC tells us the low number: how far above it our bid was, as a percentage of our bid.",
        ),
        (
            "Estimating hours",
            "Time an estimator spends on a takeoff and a price. The scarce resource: we can only bid so many jobs a month.",
        ),
        (
            "Dollars won per estimating hour",
            "Value of the work we won divided by all the estimating hours spent, won or lost. The return on the estimating team's time.",
        ),
        (
            "Win odds",
            "The model's estimate of the chance we win a given bid, from 0 % to 100 %, based on what happened on similar bids in our history.",
        ),
        (
            "Expected value (EV)",
            "Win odds × expected revenue × the margin we actually realise on that kind of work, minus the cost of estimating it. The margin dollars a bid is worth before we know the outcome.",
        ),
        (
            "EV per estimating hour",
            "Expected value divided by the hours the estimate will take. The ranking number on the scorecard.",
        ),
        ("Backlog", "Won work that still has to go through the shop, in tons."),
        (
            "Weighted pipeline",
            "Upcoming opportunities counted at their win odds: a 400-ton job we have a 25 % chance of winning counts as 100 tons.",
        ),
        (
            "Shop load / utilisation",
            "Tons scheduled in a week divided by what the shop can fabricate in a week. Above 100 % means overtime, outsourcing or late deliveries.",
        ),
        (
            "Delivery method",
            "How the project is bought. Hard bid: lowest price wins. CM at risk and design-build: the GC chooses on more than price. Negotiated: we are asked to price it without competition.",
        ),
        (
            "Complexity",
            "1 to 5. 1 is simple braced frames; 5 is architecturally exposed steel, long spans or heavy moment connections.",
        ),
        (
            "Relationship class",
            "A first-cut grouping of general contractors: A awards us often and the work earns its margin; B awards us sometimes; C rarely awards us. 'New / thin' means fewer than three bids with them.",
        ),
        (
            "Pursue / Review / Pass",
            "Pursue: worth the estimating hours, no concerns. Review: worth discussing because something is tight (shop load, distance, margin history). Pass: low odds, no capacity, or the expected value does not pay for the estimate.",
        ),
    ]
    rows = "".join(f"<tr><td><b>{_e(t)}</b></td><td>{_e(d)}</td></tr>" for t, d in terms)
    return f"<div class='card'><table class='glossary'><tbody>{rows}</tbody></table></div>"


# ------------------------------------------------------------------ page
CSS = """
:root{--surface:#fcfcfb;--page:#f3f3f0;--ink:#0b0b0b;--ink-2:#52514e;--ink-muted:#898781;--grid:#e1e0d9;--line:#d6d5cd;--good:#0ca30c;--warn:#fab219;--accent:#2a78d6}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--surface:#1c1c1a;--page:#121211;--ink:#f2f1ec;--ink-2:#c9c7bf;--ink-muted:#8f8d85;--grid:#2e2e2b;--line:#3a3a36}}
:root[data-theme="dark"]{--surface:#1c1c1a;--page:#121211;--ink:#f2f1ec;--ink-2:#c9c7bf;--ink-muted:#8f8d85;--grid:#2e2e2b;--line:#3a3a36}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 Inter,system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1240px;margin:0 auto;padding:24px 16px 64px}
header{border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:24px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:40px 0 4px}h3{font-size:14px;margin:0 0 10px;color:var(--ink-2);font-weight:600}
.sub{color:var(--ink-2);margin:0}.lede{color:var(--ink-2);margin:0 0 14px;max-width:900px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.tile-v{font-size:28px;font-weight:700;letter-spacing:-.02em}.tile-l{font-size:13px;color:var(--ink-2)}.tile-n{font-size:12px;color:var(--ink-muted);margin-top:4px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px}
@media (max-width:900px){.grid2{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px;overflow:auto;margin-bottom:14px}
.foot{font-size:12px;color:var(--ink-muted);margin:8px 0 0}
.legend{display:flex;gap:16px;font-size:12px;color:var(--ink-2);margin-top:6px}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:middle}
table{border-collapse:collapse;width:100%;font-size:13px}th{text-align:left;color:var(--ink-2);font-weight:600;border-bottom:1px solid var(--line);padding:6px 8px;white-space:nowrap}
td{padding:6px 8px;border-bottom:1px solid var(--grid);vertical-align:top;white-space:nowrap}td:first-child{white-space:normal}
table.dense{font-size:12.5px}table.dense td,table.dense th{padding:5px 6px}.why{white-space:normal;color:var(--ink-2);font-size:12px;min-width:220px;max-width:320px;display:inline-block}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid transparent}
.rec-good{background:rgba(12,163,12,.14);color:#0a7a0a;border-color:rgba(12,163,12,.35)}.rec-warn{background:rgba(250,178,25,.16);color:#8a5a00;border-color:rgba(250,178,25,.45)}.rec-muted{background:var(--grid);color:var(--ink-2)}
:root[data-theme="dark"] .rec-good,:root:not([data-theme="light"]) .rec-good{color:#7ddc7d}:root[data-theme="dark"] .rec-warn{color:#ffd37a}
.cls-A{background:rgba(42,120,214,.14);color:#1b4f8f;border-color:rgba(42,120,214,.35)}.cls-B{background:var(--grid);color:var(--ink-2)}.cls-C{background:rgba(236,131,90,.16);color:#9a3f16}.cls-N{color:var(--ink-muted)}
.findings{padding-left:20px}.findings li{margin-bottom:12px;max-width:980px}.action{display:block;color:var(--ink-2);font-size:14px;margin-top:2px}
.muted{color:var(--ink-muted)}nav{font-size:13px;color:var(--ink-2);margin-top:10px}nav a{color:var(--accent);text-decoration:none;margin-right:14px}
.note{background:var(--surface);border:1px dashed var(--line);border-radius:10px;padding:10px 14px;font-size:13px;color:var(--ink-2)}
.howto{background:var(--surface);border:1px solid var(--accent);border-radius:10px;padding:14px 18px;margin:16px 0}.howto h3{margin:0 0 8px;color:var(--ink)}.howto ol{margin:0;padding-left:20px}.howto li{margin-bottom:4px}.howto p{margin:8px 0 0;font-size:13px;color:var(--ink-2)}
table.glossary td{white-space:normal;vertical-align:top}table.glossary td:first-child{width:200px}
"""


def render(ctx: dict) -> str:
    today = ctx["snapshot_date"]
    f = ctx["fct_bids"]
    meta = f"{len(f):,} bids from {f.bid_date.min():%b %Y} to {today:%b %Y} · {int(f.is_won.sum())} jobs · {len(ctx['customer_scorecard']):,} general contractors · {len(ctx['scorecard'])} pipeline opportunities · generated {datetime.now():%Y-%m-%d %H:%M}"
    body = (
        "<header>"
        "<h1>Weibee Steel · Bid intelligence</h1>"
        "<p class='sub'>Where we win, what it actually earns, and which of the next two years' opportunities deserve estimating hours.</p>"
        f"<p class='sub muted' style='font-size:13px'>{_e(meta)}</p>"
        "<nav><a href='#findings'>Findings</a><a href='#hit'>Hit rate</a><a href='#customers'>Customers</a><a href='#execution'>Estimate vs actual</a><a href='#pricing'>Pricing feedback</a><a href='#capacity'>Capacity</a><a href='#scorecard'>Bid / no-bid</a><a href='#model'>Trusting the odds</a><a href='#glossary'>Glossary</a></nav>"
        "</header>"
        "<div class='howto'><h3>How to read this page in two minutes</h3><ol>"
        "<li><b>The six numbers at the top</b> say how the business is doing right now: how often we win, what we won, how full the shop is, and how much margin we keep.</li>"
        "<li><b>Findings</b> are the seven things the data says, each with a next action. If you read nothing else, read these.</li>"
        "<li><b>The charts</b> show where the numbers come from. Hover over any bar or line for the detail.</li>"
        "<li><b>The bid / no-bid scorecard</b> is the decision tool: every upcoming project ranked, with a Pursue / Review / Pass call and the reasons in plain words.</li>"
        "<li><b>The last section</b> says how much to trust the win odds. Short version: good enough to rank, not good enough to overrule the room on one job.</li>"
        "</ol><p>Words like <i>hit rate</i>, <i>gross margin</i> and <i>win odds</i> are explained in the <a href='#glossary'>glossary</a> at the bottom.</p></div>"
        "<p class='note'><b>Work sample on synthetic data.</b> Every number here comes from a seeded, generated bid history built to look like a mid-size Oklahoma fabricator-erector. Nothing is Weibee Steel's data. The pipeline, the marts and the scorecard logic are what would run on the real thing; see the README for what the intake would need to capture.</p>"
        + headline_tiles(ctx)
        + section(
            "findings",
            "Findings",
            "Computed from the marts, not typed in. Each has a next action.",
            findings(ctx),
        )
        + section(
            "hit",
            "Hit rate: where we win",
            "Decided bids only. The dashed line is the overall hit rate; what matters is the spread around it and the dollars won per estimating hour.",
            hit_rate_section(ctx),
        )
        + section(
            "customers",
            "Customers: who awards us, and what the work is worth",
            "Hit rate alone flatters GCs who send us everything; realised margin, change-order behaviour and payment speed belong next to it.",
            customers_section(ctx),
        )
        + section(
            "execution",
            "Estimate vs actual: what the work really earns",
            "The estimate is a forecast. Comparing it to the job's final numbers, by type and complexity, is the feedback loop that makes the next estimate better.",
            execution_section(ctx),
        )
        + section(
            "pricing",
            "Pricing feedback: how far off were we?",
            "Collected from GCs after award. The distribution says whether a loss is a markup problem or a fit problem.",
            pricing_section(ctx),
        )
        + section(
            "capacity",
            "Capacity: can the shop take what we are chasing?",
            "Won work spread over fabrication windows, plus pipeline opportunities weighted by their win odds, against shop capacity.",
            capacity_section(ctx),
        )
        + section(
            "scorecard",
            "Bid / no-bid scorecard",
            "Every upcoming opportunity scored on win odds, realised margin, estimating cost, shop load and fit. A starting point for the weekly bid meeting; the room overrides it with judgement and the override is logged.",
            scorecard_section(ctx),
        )
        + section(
            "model",
            "Model card",
            "A regularised logistic regression on our own bid history, evaluated out of time. Small, interpretable, re-fit quarterly.",
            model_section(ctx),
        )
        + "<footer class='muted' style='margin-top:40px;font-size:12px'>Built with Python, DuckDB and plain SVG. Pipeline: synthetic history → DuckDB marts (SQL) → win model → scorecard → this page.</footer>"
    )
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Weibee Bid Intelligence</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"
