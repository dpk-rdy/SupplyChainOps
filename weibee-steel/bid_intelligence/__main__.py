"""Run the whole pipeline.

python -m bid_intelligence run [--seed 42] [--out output] [--db output/warehouse.duckdb]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

from bid_intelligence import insights, report, scorecard, synth
from bid_intelligence import warehouse as W
from bid_intelligence import win_model as M


def run(
    seed: int = 5, out: str | Path = "output", db: str | Path | None = None, snapshot: str = "2026-09-28"
) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(exist_ok=True)
    t0 = time.time()

    def log(msg: str) -> None:
        print(f"[{time.time() - t0:5.1f}s] {msg}", file=sys.stderr)

    frames = synth.generate(seed=seed)
    for name, frame in frames.items():
        if not name.startswith("_"):
            frame.to_csv(out / "data" / f"{name}.csv", index=False)
    log(
        f"synthetic history: {len(frames['bids'])} bids, {len(frames['jobs'])} jobs, {len(frames['pipeline'])} pipeline opportunities"
    )

    con = W.connect(db)
    W.load_raw(con, frames)
    built = W.build_marts(con, "base")
    log(f"marts: {', '.join(built)}")

    fct_bids = W.df(con, "select * from analytics.fct_bids")
    model = M.train(fct_bids)
    log(
        f"win model: test AUC {model.diagnostics['test']['auc']:.2f} on {model.diagnostics['test']['n']} held-out bids"
    )

    sc = scorecard.score_pipeline(
        frames["pipeline"],
        fct_bids,
        frames["customers"],
        W.df(con, "select * from analytics.mart_customer_scorecard"),
        W.df(con, "select * from analytics.mart_estimate_vs_actual"),
        W.df(con, "select * from analytics.mart_backlog_weekly"),
        model,
    )
    W.write_table(con, "pipeline_scorecard", sc)
    W.build_marts(con, "final")
    log(f"scorecard: {sc.recommendation.value_counts().to_dict()}")

    ctx = {
        "snapshot_date": pd.Timestamp(snapshot),
        "fct_bids": fct_bids,
        "quarterly": W.df(con, "select * from analytics.mart_bid_results_quarterly"),
        "hit_rate_by_dimension": W.df(con, "select * from analytics.mart_hit_rate_by_dimension"),
        "customer_scorecard": W.df(con, "select * from analytics.mart_customer_scorecard"),
        "estimate_vs_actual": W.df(con, "select * from analytics.mart_estimate_vs_actual"),
        "pricing_feedback": W.df(con, "select * from analytics.mart_pricing_feedback"),
        "capacity_weekly": W.df(con, "select * from analytics.mart_capacity_weekly"),
        "scorecard": sc,
        "model_diagnostics": model.diagnostics,
        "model_coefficients": model.coefficients(),
    }
    ctx["insights"] = insights.generate(ctx)

    html = report.render(ctx)
    (out / "bid_intelligence_report.html").write_text(html)
    sc.to_csv(out / "pipeline_scorecard.csv", index=False)
    ctx["customer_scorecard"].to_csv(out / "customer_scorecard.csv", index=False)
    ctx["hit_rate_by_dimension"].to_csv(out / "hit_rate_by_dimension.csv", index=False)
    ctx["estimate_vs_actual"].to_csv(out / "estimate_vs_actual.csv", index=False)
    ctx["capacity_weekly"].to_csv(out / "capacity_weekly.csv", index=False)
    (out / "model_card.json").write_text(
        json.dumps(
            {
                "diagnostics": model.diagnostics,
                "coefficients": model.coefficients().to_dict(orient="records"),
            },
            indent=2,
            default=str,
        )
    )
    (out / "findings.md").write_text(
        "# Findings\n\n"
        + "\n".join(f"**{i['title']}.** {i['text']}\n\n→ {i['action']}\n" for i in ctx["insights"])
    )
    log(f"report: {out / 'bid_intelligence_report.html'} ({len(html) / 1024:.0f} kB)")
    con.close()
    return ctx


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bid_intelligence")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="generate data, build marts, fit model, score pipeline, render report")
    r.add_argument("--seed", type=int, default=5)
    r.add_argument("--out", default="output")
    r.add_argument("--db", default=None, help="DuckDB file to keep (default: in-memory)")
    args = p.parse_args(argv)
    if args.cmd == "run":
        run(seed=args.seed, out=args.out, db=args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
