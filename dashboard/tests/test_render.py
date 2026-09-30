import pandas as pd

from dashboard import render


def _frames():
    weeks = pd.date_range("2018-01-01", periods=8, freq="W-MON")
    service = pd.DataFrame(
        {
            "week_start": list(weeks) * 2,
            "macro_region": ["Sudeste"] * 8 + ["Norte"] * 8,
            "delivered_orders": 100,
            "on_time_rate": 0.9,
            "avg_delivery_days": 10.0,
        }
    )
    return {
        "headline": pd.DataFrame(
            [
                {
                    "orders": 1000,
                    "delivered_orders": 950,
                    "on_time_rate": 0.93,
                    "margin_per_order": 19.4,
                    "cost_per_delivery": 22.8,
                    "gmv": 1.3e6,
                    "delivery_cost": 21000.0,
                    "contribution_margin": 19400.0,
                }
            ]
        ),
        "service": service,
        "unit_economics": pd.DataFrame(
            {
                "month_start": pd.date_range("2018-01-01", periods=3, freq="MS"),
                "orders": [10, 20, 30],
                "margin_per_order": [18.0, 19.0, 20.0],
                "cost_per_delivery": [22.0, 23.0, 21.0],
                "revenue_per_order": [50.0] * 3,
                "cost_per_order": [30.0] * 3,
                "avg_order_value": [130.0] * 3,
            }
        ),
        "states": pd.DataFrame(
            [
                {
                    "state_code": "SP",
                    "macro_region": "Sudeste",
                    "orders": 500,
                    "on_time_rate": 0.95,
                    "avg_delivery_days": 8.5,
                    "margin_per_order": 18.2,
                    "cost_per_delivery": 15.1,
                    "avg_order_value": 120.0,
                }
            ]
        ),
        "demand": pd.DataFrame(
            {
                "week_start": weeks,
                "orders": [100.0] * 6 + [None, None],
                "forecast": [None] * 6 + [105.0, 110.0],
                "forecast_lower": [None] * 6 + [90.0, 92.0],
                "forecast_upper": [None] * 6 + [120.0, 130.0],
                "model_name": [None] * 6 + ["holt_damped"] * 2,
            }
        ),
        "accuracy_demand": pd.DataFrame(
            {
                "region_code": ["Sudeste", "Norte"],
                "model_name": ["holt_damped", "moving_average_4"],
                "wape": [0.2, 0.4],
                "smape": [0.2, 0.4],
                "bias": [1.0, -2.0],
            }
        ),
        "accuracy_delivery": pd.DataFrame(),
    }


def test_build_html_contains_tiles_charts_and_table():
    html = render.build_html(_frames(), "2018-01-01", "2018-03-31")
    assert "On-time delivery rate" in html and "93.0%" in html
    assert "R$ 19.40" in html and "R$ 22.80" in html
    assert html.count('class="chart"') == 5  # accuracy_delivery is empty -> skipped
    assert "State scorecard" in html and "<td>SP</td>" in html
    assert "plotly" in html.lower()


def test_unit_economics_uses_two_panels_not_dual_axis():
    fig = render.fig_unit_economics(_frames()["unit_economics"])
    assert "yaxis2" in fig.layout and fig.layout.yaxis2.overlaying is None
