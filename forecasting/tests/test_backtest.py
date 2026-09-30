import numpy as np

from forecasting import backtest as bt


def test_metrics_on_known_values():
    actual = np.array([10.0, 20.0, 30.0])
    forecast = np.array([12.0, 18.0, 33.0])
    assert bt.mae(actual, forecast) == 7 / 3
    assert bt.bias(actual, forecast) == 1.0
    assert abs(bt.wape(actual, forecast) - 7 / 60) < 1e-12
    assert bt.smape(np.array([0.0]), np.array([0.0])) == 0.0


def test_rolling_origins_respect_min_history():
    origins = bt.rolling_origin_folds(n_obs=40, horizon=8, folds=3, min_history=30)
    # candidates: 31, 30, 29 -> 29 has 30 obs of history (index 29 => 30 points) -> kept
    assert origins == [29, 30, 31]
    assert bt.rolling_origin_folds(n_obs=20, horizon=8, folds=3, min_history=30) == []


def test_backtest_series_perfect_model_has_zero_error():
    y = np.arange(1, 51, dtype=float)

    class Oracle:
        name = "oracle"

        def fit(self, y, exog=None):
            self.last = y[-1]
            return self

        def predict(self, h):
            return self.last + np.arange(1, h + 1)

    results = bt.backtest_series(y, lambda _origin: Oracle(), horizon=4, folds=3, min_history=10)
    assert len(results) == 3
    summary = bt.summarise(results)
    assert summary.loc[summary.horizon_weeks == 0, "wape"].item() == 0.0
    assert set(summary.horizon_weeks) == {0, 1, 2, 3, 4}
    q = bt.residual_quantiles(results, (0.1, 0.9))
    assert q[1] == (0.0, 0.0)
