"""Train, backtest and publish weekly demand and delivery-time forecasts by region.

    python -m forecasting.run [--backend duckdb|bigquery] [--horizon 8] [--folds 6]

For each series (orders per week, average delivery days per week) and each region
(every state, every macro-region and the national total) the job:

1. reads the weekly dbt mart and trims the incomplete tail of the Olist export,
2. backtests every candidate model on rolling origins (one week apart),
3. picks the champion per region by out-of-sample WAPE,
4. refits the champion on full history and forecasts the next ``horizon`` weeks with
   empirical prediction intervals,
5. appends forecasts, accuracy metrics and run metadata to the ``forecasts`` schema so
   accuracy is tracked across runs.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from forecasting import backtest as bt
from forecasting.config import ForecastConfig, SeriesSpec
from forecasting.models import UNIVARIATE_MODELS, BaseModel, PooledGBM
from forecasting.warehouse_io import connect

log = logging.getLogger("forecasting")

REGION_STATE, REGION_MACRO, REGION_COUNTRY = "state", "macro_region", "country"


# ------------------------------------------------------------------------ data prep
def trim_incomplete_tail(weekly: pd.DataFrame, share: float) -> pd.DataFrame:
    """Drop trailing weeks whose national volume collapses (partial export weeks)."""
    totals = weekly.groupby("week_start")["volume"].sum().sort_index()
    if len(totals) < 10:
        return weekly
    keep_until = totals.index[-1]
    for i in range(len(totals) - 1, 8, -1):
        reference = totals.iloc[i - 8 : i].median()
        if totals.iloc[i] >= share * reference:
            keep_until = totals.index[i]
            break
    return weekly[weekly["week_start"] <= keep_until]


def build_panel(mart: pd.DataFrame, spec: SeriesSpec) -> pd.DataFrame:
    """Long frame with columns region_level, region_code, week_start, value, volume."""
    df = mart.copy()
    df["week_start"] = pd.to_datetime(df["week_start"])
    df["volume"] = df[spec.weight_column] if spec.weight_column else df[spec.value_column]

    frames = []
    state = df[["state_code", "macro_region", "week_start", spec.value_column, "volume"]].rename(
        columns={spec.value_column: "value"}
    )
    frames.append(state.assign(region_level=REGION_STATE, region_code=state["state_code"]))

    for level, key in ((REGION_MACRO, "macro_region"), (REGION_COUNTRY, None)):
        g = state.assign(_key=state[key] if key else "BR")
        if spec.aggregate == "sum":
            agg = g.groupby(["_key", "week_start"], as_index=False).agg(
                value=("value", "sum"), volume=("volume", "sum")
            )
        else:
            g = g.assign(_wv=g["value"] * g["volume"])
            agg = g.groupby(["_key", "week_start"], as_index=False).agg(
                _wv=("_wv", "sum"), volume=("volume", "sum")
            )
            agg["value"] = agg["_wv"] / agg["volume"]
            agg = agg.drop(columns="_wv")
        frames.append(agg.rename(columns={"_key": "region_code"}).assign(region_level=level))

    panel = pd.concat(frames, ignore_index=True)[
        ["region_level", "region_code", "week_start", "value", "volume"]
    ]
    return panel


def complete_weeks(panel: pd.DataFrame, spec: SeriesSpec) -> pd.DataFrame:
    """Reindex every region onto the full weekly calendar; fill gaps (0 demand / carried level)."""
    weeks = pd.date_range(panel["week_start"].min(), panel["week_start"].max(), freq="W-MON")
    out = []
    for (level, code), g in panel.groupby(["region_level", "region_code"]):
        s = g.set_index("week_start").reindex(weeks)
        if spec.aggregate == "sum":
            s["value"] = s["value"].fillna(0.0)
            s["volume"] = s["volume"].fillna(0.0)
        else:
            s["value"] = s["value"].ffill().bfill()
            s["volume"] = s["volume"].fillna(0.0)
        s["region_level"], s["region_code"] = level, code
        out.append(s.rename_axis("week_start").reset_index())
    return pd.concat(out, ignore_index=True)


# ------------------------------------------------------------------------ modelling
def _pooled_fitted_to(
    panel: pd.DataFrame, cutoff_index: int, spec: SeriesSpec, seed: int, cache: dict
) -> PooledGBM:
    """Fit (and memoise) the pooled model on all state-level series up to ``cutoff_index``."""
    if cutoff_index in cache:
        return cache[cutoff_index]
    states = panel[panel["region_level"] == REGION_STATE]
    weeks = np.sort(states["week_start"].unique())[: cutoff_index + 1]
    values = {}
    exog = {}
    for code, g in states.groupby("region_code"):
        g = g.sort_values("week_start")
        values[code] = g["value"].to_numpy()[: cutoff_index + 1]
        if spec.aggregate == "weighted_mean":
            exog[code] = pd.DataFrame({"log_volume": np.log1p(g["volume"].to_numpy()[: cutoff_index + 1])})
    model = PooledGBM(random_seed=seed, log_target=spec.aggregate == "sum").fit(values, weeks, exog or None)
    cache[cutoff_index] = model
    return model


def _univariate_factory(prototype: BaseModel) -> Callable[[int], BaseModel]:
    """Return a factory that builds a fresh copy of ``prototype`` for each backtest origin."""
    params = {k: v for k, v in vars(prototype).items() if k in ("window", "season", "phi")}
    cls = type(prototype)
    return lambda _origin: cls(**params)


def _pooled_factory(
    panel: pd.DataFrame, spec: SeriesSpec, seed: int, cache: dict, region: str
) -> Callable[[int], BaseModel]:
    return lambda origin: _pooled_fitted_to(panel, origin, spec, seed, cache).for_region(region)


def forecast_series(
    panel: pd.DataFrame, spec: SeriesSpec, cfg: ForecastConfig, run_id: str, run_at: datetime
):
    """Backtest, select and forecast every region of one series. Returns (forecasts, accuracy)."""
    forecasts, accuracy = [], []
    pooled_cache: dict[int, PooledGBM] = {}
    weeks_all = np.sort(panel["week_start"].unique())
    n_weeks = len(weeks_all)
    origin_week = pd.Timestamp(weeks_all[-1])

    for (level, code), g in panel.groupby(["region_level", "region_code"]):
        g = g.sort_values("week_start")
        y = g["value"].to_numpy(dtype=float)
        mean_volume = float(g["volume"].tail(12).mean())
        candidates: dict[str, Callable[[int], BaseModel]] = {
            m.name: _univariate_factory(m) for m in UNIVARIATE_MODELS
        }
        if level == REGION_STATE and mean_volume >= spec.min_weekly_volume:
            candidates["pooled_gbm"] = _pooled_factory(panel, spec, cfg.random_seed, pooled_cache, code)
        if mean_volume < spec.min_weekly_volume:
            candidates = {"moving_average_4": candidates["moving_average_4"]}

        results_by_model = {}
        for name, factory in candidates.items():
            results_by_model[name] = bt.backtest_series(
                y, factory, cfg.horizon_weeks, cfg.backtest_folds, cfg.min_history_weeks, spec.non_negative
            )

        # champion = lowest overall WAPE (ties -> simplest model, i.e. candidate order)
        scores = {
            name: bt.summarise(res).iloc[0]["wape"] if res else np.inf
            for name, res in results_by_model.items()
        }
        champion = min(scores, key=lambda k: (np.nan_to_num(scores[k], nan=np.inf), list(scores).index(k)))

        for name, res in results_by_model.items():
            summary = bt.summarise(res)
            for _, row in summary.iterrows():
                accuracy.append(
                    {
                        "run_id": run_id,
                        "run_at": run_at,
                        "series": spec.name,
                        "region_level": level,
                        "region_code": code,
                        "model_name": name,
                        "horizon_weeks": int(row["horizon_weeks"]),
                        "n_folds": int(row["n_folds"]),
                        "mae": float(row["mae"]),
                        "smape": float(row["smape"]),
                        "wape": float(row["wape"]),
                        "bias": float(row["bias"]),
                        "is_champion": name == champion,
                        "train_end_week": origin_week,
                        "n_train_weeks": n_weeks,
                    }
                )

        # refit champion on full history and forecast
        model = candidates[champion](n_weeks - 1).fit(y)
        fc = np.asarray(model.predict(cfg.horizon_weeks), dtype=float)
        if spec.non_negative:
            fc = np.clip(fc, 0, None)
        q = bt.residual_quantiles(results_by_model[champion], cfg.interval_quantiles)
        for h in range(1, cfg.horizon_weeks + 1):
            lo, hi = q.get(h, (0.0, 0.0))
            forecasts.append(
                {
                    "run_id": run_id,
                    "run_at": run_at,
                    "series": spec.name,
                    "region_level": level,
                    "region_code": code,
                    "model_name": champion,
                    "origin_week": origin_week,
                    "week_start": origin_week + pd.Timedelta(weeks=h),
                    "horizon_weeks": h,
                    "forecast": float(fc[h - 1]),
                    "forecast_lower": float(
                        max(min(fc[h - 1] + lo, fc[h - 1]), 0.0 if spec.non_negative else -np.inf)
                    ),
                    "forecast_upper": float(max(fc[h - 1] + hi, fc[h - 1])),
                    "backtest_wape": float(scores[champion]),
                }
            )
        log.info("%s %s/%s champion=%s wape=%.3f", spec.name, level, code, champion, scores[champion])

    return pd.DataFrame(forecasts), pd.DataFrame(accuracy)


# ------------------------------------------------------------------------ entry point
def run(cfg: ForecastConfig, warehouse=None) -> dict[str, pd.DataFrame]:
    wh = warehouse or connect(cfg.backend, cfg.duckdb_path, cfg.gcp_project)
    run_id = uuid.uuid4().hex[:12]
    run_at = datetime.now(UTC).replace(tzinfo=None)
    outputs: dict[str, pd.DataFrame] = {}
    run_rows = []
    for spec in cfg.series:
        mart = wh.read_table(cfg.analytics_schema, spec.mart)
        panel = build_panel(mart, spec)
        panel = trim_incomplete_tail(panel, cfg.incomplete_tail_share)
        if spec.aggregate == "weighted_mean" and cfg.censor_tail_weeks_for_weighted_mean > 0:
            cutoff = np.sort(panel["week_start"].unique())[-(cfg.censor_tail_weeks_for_weighted_mean + 1)]
            panel = panel[panel["week_start"] <= cutoff]
        panel = complete_weeks(panel, spec)
        forecasts, accuracy = forecast_series(panel, spec, cfg, run_id, run_at)
        wh.append(cfg.forecast_schema, spec.output_table, forecasts)
        wh.append(cfg.forecast_schema, "forecast_accuracy", accuracy)
        outputs[spec.output_table] = forecasts
        outputs.setdefault("forecast_accuracy", pd.DataFrame())
        outputs["forecast_accuracy"] = pd.concat([outputs["forecast_accuracy"], accuracy], ignore_index=True)
        champ = accuracy[(accuracy["is_champion"]) & (accuracy["horizon_weeks"] == 0)]
        run_rows.append(
            {
                "run_id": run_id,
                "run_at": run_at,
                "series": spec.name,
                "train_start_week": panel["week_start"].min(),
                "train_end_week": panel["week_start"].max(),
                "n_regions": int(panel.groupby(["region_level", "region_code"]).ngroups),
                "horizon_weeks": cfg.horizon_weeks,
                "backtest_folds": cfg.backtest_folds,
                "median_champion_wape": float(champ["wape"].median()),
                "country_champion_model": str(
                    champ.loc[champ["region_level"] == REGION_COUNTRY, "model_name"].iloc[0]
                ),
                "country_champion_wape": float(
                    champ.loc[champ["region_level"] == REGION_COUNTRY, "wape"].iloc[0]
                ),
                "config_json": json.dumps(
                    {
                        "horizon_weeks": cfg.horizon_weeks,
                        "backtest_folds": cfg.backtest_folds,
                        "min_history_weeks": cfg.min_history_weeks,
                        "incomplete_tail_share": cfg.incomplete_tail_share,
                    }
                ),
            }
        )
    runs = pd.DataFrame(run_rows)
    wh.append(cfg.forecast_schema, "forecast_runs", runs)
    outputs["forecast_runs"] = runs
    if warehouse is None:
        wh.close()
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--backend", default=None, choices=["duckdb", "bigquery"])
    parser.add_argument("--horizon", type=int, default=None)
    parser.add_argument("--folds", type=int, default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    overrides = {
        k: v
        for k, v in {
            "backend": args.backend,
            "horizon_weeks": args.horizon,
            "backtest_folds": args.folds,
        }.items()
        if v is not None
    }
    cfg = ForecastConfig(**overrides)
    outputs = run(cfg)
    runs = outputs["forecast_runs"]
    print("\nForecast run summary")
    print(
        runs[
            [
                "run_id",
                "series",
                "train_end_week",
                "n_regions",
                "country_champion_model",
                "country_champion_wape",
                "median_champion_wape",
            ]
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
