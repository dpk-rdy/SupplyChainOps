"""Render the operations KPI dashboard to a self-contained HTML file from the warehouse.

    python -m dashboard.render [--start 2017-01-01] [--end 2018-08-31] [--out dashboard/output/kpi_dashboard.html]

This is the local, credential-free rendering of the same pages that are built in Looker
Studio / Power BI on BigQuery (see dashboard/README.md). It is used to verify the marts and
to keep a reviewable artefact in CI.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dashboard import palette as P
from dashboard import queries as Q

DEFAULT_START, DEFAULT_END = "2017-01-01", "2018-08-19"  # last complete week of the Olist export
REGION_ORDER = ["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]


# ------------------------------------------------------------------ data access
def load_frames(
    con,
    schema: str = "analytics",
    forecast_schema: str = "forecasts",
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
) -> dict[str, pd.DataFrame]:
    fmt = dict(schema=schema, forecast_schema=forecast_schema, start=start, end=end)
    frames = {
        "headline": con.execute(Q.HEADLINE.format(**fmt)).df(),
        "service": con.execute(Q.WEEKLY_SERVICE_BY_REGION.format(**fmt)).df(),
        "unit_economics": con.execute(Q.MONTHLY_UNIT_ECONOMICS.format(**fmt)).df(),
        "states": con.execute(Q.STATE_SCORECARD.format(**fmt)).df(),
    }
    try:
        frames["demand"] = con.execute(Q.DEMAND_ACTUAL_VS_FORECAST.format(**fmt)).df()
        frames["accuracy_demand"] = con.execute(
            Q.FORECAST_ACCURACY_BY_REGION.format(series="demand_orders", **fmt)
        ).df()
        frames["accuracy_delivery"] = con.execute(
            Q.FORECAST_ACCURACY_BY_REGION.format(series="delivery_days", **fmt)
        ).df()
    except Exception:  # noqa: BLE001 - forecast tables are optional (run `make forecast`)
        frames["demand"] = pd.DataFrame()
    return frames


# ------------------------------------------------------------------ figure helpers
def _layout(fig: go.Figure, title: str, y_title: str = "", height: int = 340) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=P.INK), x=0, xanchor="left"),
        paper_bgcolor=P.SURFACE,
        plot_bgcolor=P.SURFACE,
        font=dict(family="Inter, system-ui, sans-serif", color=P.INK_SECONDARY, size=12),
        margin=dict(l=48, r=24, t=56, b=40),
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.18, x=0, font=dict(color=P.INK_SECONDARY)),
    )
    fig.update_xaxes(showgrid=False, linecolor=P.AXIS, tickfont=dict(color=P.INK_MUTED), zeroline=False)
    fig.update_yaxes(
        title=y_title,
        gridcolor=P.GRID,
        gridwidth=1,
        linecolor=P.SURFACE,
        tickfont=dict(color=P.INK_MUTED),
        zeroline=False,
    )
    return fig


def fig_on_time_by_region(service: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for region in REGION_ORDER:
        g = service[service.macro_region == region]
        if g.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=g.week_start,
                y=g.on_time_rate,
                name=region,
                mode="lines",
                line=dict(color=P.MACRO_REGION_COLORS[region], width=2),
                hovertemplate="%{y:.1%}<extra>" + region + "</extra>",
            )
        )
    fig.update_yaxes(tickformat=".0%", range=[0.4, 1.02])
    return _layout(fig, "On-time delivery rate by macro-region, weekly", "share of delivered orders")


def fig_delivery_days_by_region(service: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for region in REGION_ORDER:
        g = service[service.macro_region == region]
        if g.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=g.week_start,
                y=g.avg_delivery_days,
                name=region,
                mode="lines",
                line=dict(color=P.MACRO_REGION_COLORS[region], width=2),
                hovertemplate="%{y:.1f} days<extra>" + region + "</extra>",
            )
        )
    return _layout(fig, "Average purchase-to-delivery time by macro-region, weekly", "days")


def fig_unit_economics(ue: pd.DataFrame) -> go.Figure:
    """Two panels, one y-axis each (never a dual axis)."""
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("Margin per order (BRL)", "Cost per delivery (BRL)"),
        horizontal_spacing=0.08,
    )
    fig.add_trace(
        go.Scatter(
            x=ue.month_start,
            y=ue.margin_per_order,
            name="Margin per order",
            mode="lines+markers",
            line=dict(color=P.CATEGORICAL[0], width=2),
            marker=dict(size=8),
            hovertemplate="R$ %{y:.2f}<extra>margin / order</extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=ue.month_start,
            y=ue.cost_per_delivery,
            name="Cost per delivery",
            mode="lines+markers",
            line=dict(color=P.CATEGORICAL[1], width=2),
            marker=dict(size=8),
            hovertemplate="R$ %{y:.2f}<extra>cost / delivery</extra>",
        ),
        row=1,
        col=2,
    )
    fig.update_layout(showlegend=False)
    return _layout(fig, "Unit economics, monthly", "BRL")


def fig_demand_forecast(demand: pd.DataFrame) -> go.Figure | None:
    if demand.empty:
        return None
    fig = go.Figure()
    fc = demand.dropna(subset=["forecast"])
    if not fc.empty:
        fig.add_trace(
            go.Scatter(
                x=pd.concat([fc.week_start, fc.week_start[::-1]]),
                y=pd.concat([fc.forecast_upper, fc.forecast_lower[::-1]]),
                fill="toself",
                fillcolor=P.FORECAST_BAND,
                line=dict(width=0),
                mode="lines",
                name="10-90% interval",
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=fc.week_start,
                y=fc.forecast,
                name=f"Forecast ({fc.model_name.iloc[0]})",
                mode="lines",
                line=dict(color=P.CATEGORICAL[0], width=2, dash="dash"),
                hovertemplate="%{y:,.0f} orders<extra>forecast</extra>",
            )
        )
    act = demand.dropna(subset=["orders"])
    if not fc.empty:  # actuals after the forecast origin are incomplete export weeks
        act = act[act.week_start < fc.week_start.min()]
    fig.add_trace(
        go.Scatter(
            x=act.week_start,
            y=act.orders,
            name="Actual orders",
            mode="lines",
            line=dict(color=P.INK, width=2),
            hovertemplate="%{y:,.0f} orders<extra>actual</extra>",
        )
    )
    return _layout(fig, "Weekly orders, Brazil: actual and 8-week forecast", "orders / week")


def fig_forecast_accuracy(acc: pd.DataFrame, title: str) -> go.Figure | None:
    if acc.empty:
        return None
    acc = acc.sort_values("wape", ascending=False)
    fig = go.Figure(
        go.Bar(
            x=acc.wape,
            y=acc.region_code,
            orientation="h",
            marker=dict(color=[P.MACRO_REGION_COLORS.get(r, P.CATEGORICAL[0]) for r in acc.region_code]),
            text=[f"{w:.0%} · {m}" for w, m in zip(acc.wape, acc.model_name, strict=True)],
            textposition="outside",
            textfont=dict(color=P.INK_SECONDARY),
            hovertemplate="WAPE %{x:.1%}<extra>%{y}</extra>",
        )
    )
    fig.update_xaxes(tickformat=".0%", range=[0, max(0.6, float(acc.wape.max()) * 1.35)])
    fig.update_layout(showlegend=False, hovermode="closest")
    return _layout(fig, title, "backtest WAPE (lower is better)", height=300)


# ------------------------------------------------------------------ page
def _tile(label: str, value: str, note: str = "") -> str:
    return f'<div class="tile"><div class="label">{label}</div><div class="value">{value}</div><div class="note">{note}</div></div>'


def _table(df: pd.DataFrame) -> str:
    cols = [
        "state_code",
        "macro_region",
        "orders",
        "on_time_rate",
        "avg_delivery_days",
        "margin_per_order",
        "cost_per_delivery",
        "avg_order_value",
    ]
    head = "".join(f"<th>{c.replace('_', ' ')}</th>" for c in cols)
    rows = []
    for _, r in df[cols].iterrows():
        cells = [
            r.state_code,
            r.macro_region,
            f"{int(r.orders):,}",
            f"{r.on_time_rate:.1%}" if pd.notna(r.on_time_rate) else "–",
            f"{r.avg_delivery_days:.1f}" if pd.notna(r.avg_delivery_days) else "–",
            f"{r.margin_per_order:.2f}",
            f"{r.cost_per_delivery:.2f}" if pd.notna(r.cost_per_delivery) else "–",
            f"{r.avg_order_value:.2f}",
        ]
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return f'<table class="scorecard"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def build_html(frames: dict[str, pd.DataFrame], start: str, end: str) -> str:
    h = frames["headline"].iloc[0]
    tiles = "".join(
        [
            _tile("Orders", f"{int(h.orders):,}", f"{start} to {end}, non-canceled"),
            _tile(
                "On-time delivery rate",
                f"{h.on_time_rate:.1%}",
                f"{int(h.delivered_orders):,} delivered orders",
            ),
            _tile(
                "Margin per order",
                f"R$ {h.margin_per_order:.2f}",
                f"R$ {h.contribution_margin:,.0f} contribution margin",
            ),
            _tile(
                "Cost per delivery",
                f"R$ {h.cost_per_delivery:.2f}",
                f"R$ {h.delivery_cost:,.0f} delivery cost",
            ),
            _tile("GMV", f"R$ {h.gmv / 1e6:.2f}M", "gross merchandise value"),
        ]
    )
    figs = [
        fig_on_time_by_region(frames["service"]),
        fig_delivery_days_by_region(frames["service"]),
        fig_unit_economics(frames["unit_economics"]),
        fig_demand_forecast(frames.get("demand", pd.DataFrame())),
        fig_forecast_accuracy(
            frames.get("accuracy_demand", pd.DataFrame()),
            "Demand forecast accuracy by macro-region (champion model)",
        ),
        fig_forecast_accuracy(
            frames.get("accuracy_delivery", pd.DataFrame()),
            "Delivery-time forecast accuracy by macro-region (champion model)",
        ),
    ]
    charts = "".join(
        f'<div class="chart">{f.to_html(full_html=False, include_plotlyjs=(i == 0), config={"displayModeBar": False, "responsive": True})}</div>'
        for i, f in enumerate([f for f in figs if f is not None])
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SupplyChainOps KPIs</title>
<style>
  :root {{ --page:{P.PAGE}; --surface:{P.SURFACE}; --ink:{P.INK}; --ink2:{P.INK_SECONDARY}; --muted:{P.INK_MUTED}; --grid:{P.GRID}; }}
  body {{ margin:0; background:var(--page); color:var(--ink); font-family: Inter, system-ui, sans-serif; padding: 24px 16px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }} .sub {{ color: var(--ink2); margin-bottom: 20px; font-size: 14px; }}
  .tiles {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .tile {{ background: var(--surface); border: 1px solid var(--grid); border-radius: 8px; padding: 14px 16px; }}
  .tile .label {{ font-size: 12px; color: var(--ink2); text-transform: uppercase; letter-spacing: .04em; }}
  .tile .value {{ font-size: 28px; font-weight: 600; font-variant-numeric: tabular-nums; margin: 4px 0; }}
  .tile .note {{ font-size: 12px; color: var(--muted); }}
  .chart {{ background: var(--surface); border: 1px solid var(--grid); border-radius: 8px; padding: 8px; margin-bottom: 16px; }}
  table.scorecard {{ width: 100%; border-collapse: collapse; background: var(--surface); font-size: 13px; font-variant-numeric: tabular-nums; }}
  table.scorecard th, table.scorecard td {{ padding: 6px 10px; border-bottom: 1px solid var(--grid); text-align: right; }}
  table.scorecard th:nth-child(-n+2), table.scorecard td:nth-child(-n+2) {{ text-align: left; }}
  table.scorecard th {{ color: var(--ink2); font-weight: 500; text-transform: capitalize; }}
  h2 {{ font-size: 16px; margin: 24px 0 8px; }}
  .method {{ font-size: 12px; color: var(--ink2); margin-top: 24px; line-height: 1.5; }}
</style></head>
<body>
<h1>SupplyChainOps — operations KPIs</h1>
<div class="sub">Olist Brazilian e-commerce, {start} to {end}. Source: dbt marts <code>mart_kpi_daily_region</code>, <code>mart_unit_economics_monthly</code>, forecast tables.</div>
<div class="tiles">{tiles}</div>
{charts}
<h2>State scorecard</h2>
{_table(frames["states"])}
<div class="method">On-time = delivered on or before the estimated delivery date, over delivered orders. Margin per order = (take rate × GMV + freight collected) − (carrier cost + payment fees + handling), using the assumptions in <code>dbt/dbt_project.yml</code>. Cost per delivery = modelled carrier cost per delivered order. Forecast accuracy = WAPE over rolling-origin backtests (6 origins × 8-week horizon).</div>
</body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--duckdb-path", default=os.environ.get("DUCKDB_PATH", "data/warehouse/supplychainops.duckdb")
    )
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out", default="dashboard/output/kpi_dashboard.html")
    args = parser.parse_args(argv)

    import duckdb

    con = duckdb.connect(args.duckdb_path, read_only=True)
    frames = load_frames(con, start=args.start, end=args.end)
    con.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(frames, args.start, args.end), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
