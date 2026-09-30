import numpy as np
import pandas as pd

from forecasting.models import HoltDamped, MovingAverage, PooledGBM, SeasonalNaive


def test_moving_average_is_flat_mean_of_window():
    y = np.array([1, 2, 3, 4, 10, 10, 10, 10], dtype=float)
    fc = MovingAverage(4).fit(y).predict(3)
    assert np.allclose(fc, 10.0)


def test_seasonal_naive_uses_last_year_scaled_by_growth():
    season = 52
    base = np.tile(np.arange(1, season + 1, dtype=float), 2)  # two identical years
    y = np.concatenate([base, base[:8] * 2])  # third year runs at 2x the level
    fc = SeasonalNaive(season).fit(y).predict(4)
    assert np.allclose(fc, base[8:12] * 2, rtol=0.05)


def test_seasonal_naive_falls_back_on_short_history():
    fc = SeasonalNaive().fit(np.arange(10, dtype=float)).predict(2)
    assert np.allclose(fc, np.mean([6, 7, 8, 9]))


def test_holt_extrapolates_trend_with_damping():
    y = np.arange(1, 41, dtype=float)
    fc = HoltDamped(phi=0.9).fit(y).predict(3)
    assert fc[0] > 40 and fc[2] > fc[1] > fc[0]
    assert fc[2] - fc[1] < fc[1] - fc[0]  # damped increments shrink


def test_pooled_gbm_predicts_every_region_with_right_shape():
    rng = np.random.default_rng(0)
    weeks = pd.date_range("2017-01-02", periods=60, freq="W-MON").to_numpy()
    values = {r: 100 * (i + 1) + rng.normal(0, 5, 60) for i, r in enumerate(["A", "B", "C"])}
    model = PooledGBM(random_seed=1).fit(values, weeks)
    fc = model.for_region("C").fit(values["C"]).predict(5)
    assert fc.shape == (5,)
    assert 250 < fc.mean() < 350  # stays near region C's level
