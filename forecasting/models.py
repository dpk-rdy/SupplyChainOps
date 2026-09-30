"""Forecasting models.

Every model implements ``fit(history, exog) -> self`` and ``predict(horizon) -> np.ndarray``
on a single weekly series. ``PooledGBM`` is the exception: it is fitted once across all
regions (a global model) and exposes the same per-series interface through ``for_region``.

Baselines are deliberately simple and dependency-free (numpy only) so the accuracy table
always has a meaningful reference point.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


class BaseModel:
    name: str = "base"

    def fit(self, y: np.ndarray, exog: pd.DataFrame | None = None) -> BaseModel:  # noqa: ARG002
        self.y_ = np.asarray(y, dtype=float)
        return self

    def predict(self, horizon: int) -> np.ndarray:
        raise NotImplementedError


class MovingAverage(BaseModel):
    """Mean of the last ``window`` observations, held flat over the horizon."""

    def __init__(self, window: int = 4):
        self.window = window
        self.name = f"moving_average_{window}"

    def predict(self, horizon: int) -> np.ndarray:
        level = float(np.mean(self.y_[-self.window :])) if len(self.y_) else 0.0
        return np.full(horizon, level)


class SeasonalNaive(BaseModel):
    """Value observed one season (52 weeks) earlier, scaled by the recent year-over-year ratio.

    Falls back to a 4-week moving average when fewer than ``season + 4`` points exist.
    """

    name = "seasonal_naive_yoy"

    def __init__(self, season: int = 52):
        self.season = season

    def predict(self, horizon: int) -> np.ndarray:
        y = self.y_
        n = len(y)
        if n < self.season + 4:
            return MovingAverage(4).fit(y).predict(horizon)
        recent = y[-4:].sum()
        last_year = y[n - self.season - 4 : n - self.season].sum()
        growth = recent / last_year if last_year > 0 else 1.0
        growth = float(np.clip(growth, 0.25, 4.0))
        out = np.empty(horizon)
        for h in range(horizon):
            idx = n + h - self.season
            out[h] = y[idx] * growth if idx >= 0 else y[-1]
        return out


class HoltDamped(BaseModel):
    """Holt's linear trend with damping (additive), parameters chosen by grid search on SSE."""

    name = "holt_damped"

    def __init__(self, phi: float = 0.9):
        self.phi = phi

    @staticmethod
    def _run(y: np.ndarray, alpha: float, beta: float, phi: float) -> tuple[float, float, float]:
        level, trend = y[0], (y[1] - y[0]) if len(y) > 1 else 0.0
        sse = 0.0
        for t in range(1, len(y)):
            forecast = level + phi * trend
            sse += (y[t] - forecast) ** 2
            new_level = alpha * y[t] + (1 - alpha) * (level + phi * trend)
            trend = beta * (new_level - level) + (1 - beta) * phi * trend
            level = new_level
        return level, trend, sse

    def fit(self, y: np.ndarray, exog: pd.DataFrame | None = None) -> HoltDamped:
        super().fit(y, exog)
        best = (np.inf, 0.5, 0.1)
        for alpha in (0.2, 0.4, 0.6, 0.8):
            for beta in (0.05, 0.1, 0.2, 0.4):
                *_, sse = self._run(self.y_, alpha, beta, self.phi)
                if sse < best[0]:
                    best = (sse, alpha, beta)
        _, self.alpha_, self.beta_ = best
        self.level_, self.trend_, _ = self._run(self.y_, self.alpha_, self.beta_, self.phi)
        return self

    def predict(self, horizon: int) -> np.ndarray:
        damp = np.cumsum([self.phi**h for h in range(1, horizon + 1)])
        return self.level_ + damp * self.trend_


# ------------------------------------------------------------------------- pooled GBM
LAGS = (1, 2, 3, 4, 6, 8)


def _feature_frame(
    values: dict[str, np.ndarray],
    weeks: np.ndarray,
    exog: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Build the supervised learning frame for the pooled model.

    ``values`` maps region -> aligned weekly series; ``weeks`` is the shared week index.
    Each row targets the next week's value given lagged values and calendar features.
    """
    rows = []
    week_of_year = pd.DatetimeIndex(weeks).isocalendar().week.to_numpy()
    for region, y in values.items():
        ex = exog.get(region) if exog else None
        for t in range(max(LAGS), len(y)):
            row = {
                "region": region,
                "t": t,
                "target": y[t] - np.mean(y[t - 4 : t]),  # deviation from the recent level (scale-free)
                "woy_sin": np.sin(2 * np.pi * week_of_year[t] / 52.18),
                "woy_cos": np.cos(2 * np.pi * week_of_year[t] / 52.18),
                "level_4": np.mean(y[t - 4 : t]),
                "level_8": np.mean(y[t - 8 : t]),
            }
            for lag in LAGS:
                row[f"lag_{lag}"] = y[t - lag]
            if ex is not None:
                for col in ex.columns:
                    row[f"exog_{col}"] = ex.iloc[t - 1][col]  # last observed value of the covariate
            rows.append(row)
    return pd.DataFrame(rows)


@dataclass
class PooledGBM:
    """One gradient-boosting model shared across regions, forecasting recursively.

    Training on all regions at once lets small states borrow strength from large ones,
    which matters for the northern states with a handful of orders per week. The target is
    the deviation from the trailing 4-week level (in log space for count series), so the
    model learns shape and seasonality rather than absolute scale and extrapolates level.
    """

    random_seed: int = 42
    log_target: bool = True
    name: str = "pooled_gbm"
    regions_: list[str] = field(default_factory=list)

    def fit(
        self, values: dict[str, np.ndarray], weeks: np.ndarray, exog: dict[str, pd.DataFrame] | None = None
    ):
        from sklearn.ensemble import HistGradientBoostingRegressor

        self.weeks_ = np.asarray(weeks)
        self.values_ = {k: np.asarray(v, dtype=float) for k, v in values.items()}
        self.exog_ = exog
        self.regions_ = list(values)
        frame = _feature_frame(self._transform(self.values_), self.weeks_, exog)
        self.feature_cols_ = [c for c in frame.columns if c not in ("target", "region", "t")]
        frame["region_code"] = pd.Categorical(frame["region"], categories=self.regions_).codes
        self.feature_cols_.append("region_code")
        X = frame[self.feature_cols_].to_numpy(dtype=float)
        self.model_ = HistGradientBoostingRegressor(
            max_iter=300,
            learning_rate=0.05,
            max_depth=4,
            min_samples_leaf=10,
            l2_regularization=1.0,
            categorical_features=[self.feature_cols_.index("region_code")],
            random_state=self.random_seed,
        )
        self.model_.fit(X, frame["target"].to_numpy(dtype=float))
        return self

    def _transform(self, values: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return {k: np.log1p(np.clip(v, 0, None)) for k, v in values.items()} if self.log_target else values

    def _inverse(self, v: np.ndarray) -> np.ndarray:
        return np.expm1(v) if self.log_target else v

    def predict_region(self, region: str, horizon: int) -> np.ndarray:
        y = self._transform({region: self.values_[region]})[region].tolist()
        ex = self.exog_.get(region) if self.exog_ else None
        last_week = pd.Timestamp(self.weeks_[-1])
        out = []
        code = self.regions_.index(region)
        for h in range(1, horizon + 1):
            t = len(y)
            week = last_week + pd.Timedelta(weeks=h)
            woy = week.isocalendar().week
            feats = {
                "woy_sin": np.sin(2 * np.pi * woy / 52.18),
                "woy_cos": np.cos(2 * np.pi * woy / 52.18),
                "level_4": np.mean(y[t - 4 : t]),
                "level_8": np.mean(y[t - 8 : t]),
            }
            for lag in LAGS:
                feats[f"lag_{lag}"] = y[t - lag]
            if ex is not None:
                for col in ex.columns:
                    feats[f"exog_{col}"] = ex.iloc[-1][col]  # hold covariates at their last value
            feats["region_code"] = code
            x = np.array([[feats[c] for c in self.feature_cols_]], dtype=float)
            pred = float(self.model_.predict(x)[0]) + feats["level_4"]
            y.append(pred)
            out.append(pred)
        return self._inverse(np.array(out))

    def for_region(self, region: str) -> _PooledView:
        return _PooledView(self, region)


class _PooledView(BaseModel):
    """Per-region adapter so the pooled model can be backtested like the univariate ones."""

    def __init__(self, pooled: PooledGBM, region: str):
        self.pooled = pooled
        self.region = region
        self.name = pooled.name

    def fit(self, y: np.ndarray, exog: pd.DataFrame | None = None) -> _PooledView:  # noqa: ARG002
        return self  # already fitted globally

    def predict(self, horizon: int) -> np.ndarray:
        return self.pooled.predict_region(self.region, horizon)


UNIVARIATE_MODELS = (MovingAverage(4), SeasonalNaive(), HoltDamped())
