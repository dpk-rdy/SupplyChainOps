"""Rolling-origin backtesting and accuracy metrics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def mae(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - forecast)))


def bias(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Mean error (forecast - actual). Positive = over-forecasting."""
    return float(np.mean(forecast - actual))


def smape(actual: np.ndarray, forecast: np.ndarray) -> float:
    denom = np.abs(actual) + np.abs(forecast)
    with np.errstate(invalid="ignore", divide="ignore"):
        terms = np.where(denom == 0, 0.0, 2.0 * np.abs(forecast - actual) / denom)
    return float(np.mean(terms))


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Weighted absolute percentage error = sum|e| / sum|y|. Robust to zero weeks."""
    denom = float(np.sum(np.abs(actual)))
    return float(np.sum(np.abs(actual - forecast)) / denom) if denom > 0 else float("nan")


@dataclass
class FoldResult:
    origin_index: int  # index of the last training observation
    horizon: np.ndarray  # 1..H
    actual: np.ndarray
    forecast: np.ndarray


def rolling_origin_folds(n_obs: int, horizon: int, folds: int, min_history: int) -> list[int]:
    """Indices of the last training observation for each fold (most recent fold last)."""
    origins = [n_obs - horizon - k - 1 for k in range(folds)]
    origins = [o for o in origins if o + 1 >= min_history]
    return sorted(origins)


def backtest_series(
    y: np.ndarray,
    make_model,
    horizon: int,
    folds: int,
    min_history: int,
    non_negative: bool = True,
) -> list[FoldResult]:
    """Fit ``make_model()`` at each origin and forecast ``horizon`` steps ahead.

    ``make_model`` is a zero-arg callable returning an unfitted model; for the pooled model,
    the caller passes a callable that returns a view of a model fitted on data up to the origin.
    """
    y = np.asarray(y, dtype=float)
    results = []
    for origin in rolling_origin_folds(len(y), horizon, folds, min_history):
        train = y[: origin + 1]
        model = make_model(origin).fit(train)
        fc = np.asarray(model.predict(horizon), dtype=float)
        if non_negative:
            fc = np.clip(fc, 0, None)
        actual = y[origin + 1 : origin + 1 + horizon]
        results.append(FoldResult(origin, np.arange(1, horizon + 1), actual, fc))
    return results


def summarise(results: list[FoldResult]) -> pd.DataFrame:
    """Per-horizon and overall metrics across folds."""
    if not results:
        return pd.DataFrame(columns=["horizon_weeks", "n_folds", "mae", "smape", "wape", "bias"])
    rows = []
    by_h: dict[int, tuple[list, list]] = {}
    for r in results:
        for h, a, f in zip(r.horizon, r.actual, r.forecast, strict=True):
            by_h.setdefault(int(h), ([], []))
            by_h[int(h)][0].append(a)
            by_h[int(h)][1].append(f)
    all_a = np.concatenate([r.actual for r in results])
    all_f = np.concatenate([r.forecast for r in results])
    rows.append(
        {
            "horizon_weeks": 0,
            "n_folds": len(results),
            "mae": mae(all_a, all_f),
            "smape": smape(all_a, all_f),
            "wape": wape(all_a, all_f),
            "bias": bias(all_a, all_f),
        }
    )
    for h, (a, f) in sorted(by_h.items()):
        a_, f_ = np.array(a), np.array(f)
        rows.append(
            {
                "horizon_weeks": h,
                "n_folds": len(a_),
                "mae": mae(a_, f_),
                "smape": smape(a_, f_),
                "wape": wape(a_, f_),
                "bias": bias(a_, f_),
            }
        )
    return pd.DataFrame(rows)


def residual_quantiles(
    results: list[FoldResult], quantiles: tuple[float, float]
) -> dict[int, tuple[float, float]]:
    """Empirical error quantiles (actual - forecast) per horizon, used for prediction intervals."""
    by_h: dict[int, list[float]] = {}
    for r in results:
        for h, a, f in zip(r.horizon, r.actual, r.forecast, strict=True):
            by_h.setdefault(int(h), []).append(float(a - f))
    out = {}
    for h, errs in by_h.items():
        e = np.array(errs)
        out[h] = (float(np.quantile(e, quantiles[0])), float(np.quantile(e, quantiles[1])))
    return out
