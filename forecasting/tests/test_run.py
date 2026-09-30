import numpy as np
import pandas as pd

from forecasting import run as fr
from forecasting.config import DELIVERY_TIME, DEMAND, ForecastConfig


def _demand_mart(n_weeks=60, states=("SP", "RJ", "AC")):
    weeks = pd.date_range("2017-01-02", periods=n_weeks, freq="W-MON")
    rows = []
    rng = np.random.default_rng(3)
    for s in states:
        level = {"SP": 500, "RJ": 150, "AC": 1}[s]
        for i, w in enumerate(weeks):
            orders = max(0, int(level * (1 + 0.01 * i) + rng.normal(0, level * 0.1)))
            rows.append(
                {
                    "week_start": w.date(),
                    "state_code": s,
                    "macro_region": "Sudeste" if s != "AC" else "Norte",
                    "orders": orders,
                    "canceled_orders": 0,
                    "items": orders,
                    "gmv": orders * 120.0,
                    "freight_value": orders * 20.0,
                    "customers": orders,
                }
            )
    return pd.DataFrame(rows)


def test_build_panel_adds_macro_and_country_levels():
    panel = fr.build_panel(_demand_mart(), DEMAND)
    levels = set(panel["region_level"])
    assert levels == {"state", "macro_region", "country"}
    br = panel[(panel.region_level == "country")].sort_values("week_start")
    states = panel[panel.region_level == "state"].groupby("week_start")["value"].sum().sort_index()
    assert np.allclose(br["value"].to_numpy(), states.to_numpy())


def test_weighted_mean_aggregation_for_delivery_days():
    mart = pd.DataFrame(
        {
            "week_start": ["2018-01-01", "2018-01-01"],
            "state_code": ["SP", "RJ"],
            "macro_region": ["Sudeste", "Sudeste"],
            "delivered_orders": [300, 100],
            "avg_delivery_days": [8.0, 12.0],
        }
    )
    panel = fr.build_panel(mart, DELIVERY_TIME)
    macro = panel[panel.region_level == "macro_region"]["value"].item()
    assert macro == (300 * 8 + 100 * 12) / 400


def test_trim_incomplete_tail_drops_partial_export_weeks():
    mart = _demand_mart(n_weeks=40)
    panel = fr.build_panel(mart, DEMAND)
    last = panel["week_start"].max()
    partial = panel[panel.region_level == "state"].copy()
    partial["week_start"] = last + pd.Timedelta(weeks=1)
    partial["value"] = partial["value"] * 0.05
    partial["volume"] = partial["value"]
    panel2 = pd.concat([panel, partial], ignore_index=True)
    trimmed = fr.trim_incomplete_tail(panel2, share=0.7)
    assert trimmed["week_start"].max() == last


def test_end_to_end_run_writes_all_tables():
    class FakeWarehouse:
        def __init__(self):
            self.tables = {}

        def read_table(self, schema, table):
            if table == DEMAND.mart:
                return _demand_mart()
            mart = _demand_mart()
            return mart.assign(
                delivered_orders=mart["orders"],
                avg_delivery_days=10.0 + (mart["orders"] % 3),
                median_delivery_days=9.0,
                on_time_rate=0.9,
            )[["week_start", "state_code", "macro_region", "delivered_orders", "avg_delivery_days"]]

        def append(self, schema, table, frame):
            self.tables.setdefault(f"{schema}.{table}", []).append(frame)

    wh = FakeWarehouse()
    cfg = ForecastConfig(horizon_weeks=4, backtest_folds=2, min_history_weeks=20)
    out = fr.run(cfg, warehouse=wh)
    assert set(wh.tables) == {
        "forecasts.forecast_demand_weekly_region",
        "forecasts.forecast_delivery_time_weekly_region",
        "forecasts.forecast_accuracy",
        "forecasts.forecast_runs",
    }
    demand = out["forecast_demand_weekly_region"]
    # 3 states + 2 macro regions + country = 6 regions x 4 horizons
    assert len(demand) == 6 * 4
    assert (demand["forecast_lower"] <= demand["forecast"]).all() and (
        demand["forecast"] <= demand["forecast_upper"]
    ).all()
    assert (demand["forecast"] >= 0).all()
    acc = out["forecast_accuracy"]
    champions = acc[(acc.is_champion) & (acc.horizon_weeks == 0)]
    assert champions.groupby(["series", "region_level", "region_code"]).size().eq(1).all()
    assert len(out["forecast_runs"]) == 2
