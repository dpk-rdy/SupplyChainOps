"""Forecasting configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeriesSpec:
    """One forecast target read from a dbt mart."""

    name: str  # series id written to the warehouse
    mart: str  # dbt model to read
    value_column: str  # column to forecast
    weight_column: str | None  # column used when aggregating states to regions (None = sum)
    aggregate: str  # 'sum' or 'weighted_mean'
    output_table: str
    min_weekly_volume: float  # below this mean level the series only gets the moving-average model
    non_negative: bool = True


DEMAND = SeriesSpec(
    name="demand_orders",
    mart="mart_demand_weekly_region",
    value_column="orders",
    weight_column=None,
    aggregate="sum",
    output_table="forecast_demand_weekly_region",
    min_weekly_volume=5.0,
)

DELIVERY_TIME = SeriesSpec(
    name="delivery_days",
    mart="mart_delivery_time_weekly_region",
    value_column="avg_delivery_days",
    weight_column="delivered_orders",
    aggregate="weighted_mean",
    output_table="forecast_delivery_time_weekly_region",
    min_weekly_volume=5.0,
)


@dataclass(frozen=True)
class ForecastConfig:
    backend: str = os.environ.get("WAREHOUSE_BACKEND", "duckdb")
    duckdb_path: str = os.environ.get("DUCKDB_PATH", "data/warehouse/supplychainops.duckdb")
    gcp_project: str | None = os.environ.get("GCP_PROJECT")
    analytics_schema: str = os.environ.get("BQ_DATASET_ANALYTICS", "analytics")
    forecast_schema: str = os.environ.get("FORECAST_SCHEMA", "forecasts")

    horizon_weeks: int = 8
    backtest_folds: int = 6  # rolling origins, one week apart
    min_history_weeks: int = 20
    # Weeks at the tail whose national volume is below this share of the trailing
    # 8-week median are treated as incomplete (Olist's export stops mid-August 2018).
    incomplete_tail_share: float = 0.7
    # Extra trailing weeks dropped for series that only observe completed deliveries
    # (the last purchase week only contains the orders already delivered = the fast ones).
    censor_tail_weeks_for_weighted_mean: int = 1
    interval_quantiles: tuple[float, float] = (0.1, 0.9)
    series: tuple[SeriesSpec, ...] = field(default_factory=lambda: (DEMAND, DELIVERY_TIME))
    random_seed: int = 42
