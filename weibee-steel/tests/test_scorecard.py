import numpy as np

from bid_intelligence import config as C
from bid_intelligence import scorecard as S
from bid_intelligence import warehouse as W
from bid_intelligence import win_model as M


def _score(con, frames):
    fct = W.df(con, "select * from analytics.fct_bids")
    model = M.train(fct, cutoff=fct.bid_date.quantile(0.75))
    return S.score_pipeline(
        frames["pipeline"],
        fct,
        frames["customers"],
        W.df(con, "select * from analytics.mart_customer_scorecard"),
        W.df(con, "select * from analytics.mart_estimate_vs_actual"),
        W.df(con, "select * from analytics.mart_backlog_weekly"),
        model,
    )


def test_scorecard_covers_every_pipeline_opportunity(con, frames):
    sc = _score(con, frames)
    assert len(sc) == len(frames["pipeline"]) and sc.opportunity_id.is_unique
    assert set(sc.recommendation) <= {"Pursue", "Review", "Pass"}
    assert sc.p_win.between(0, 1).all()
    assert (sc["rank"].sort_values().to_numpy() == np.arange(1, len(sc) + 1)).all()
    assert sc.ev_per_est_hour.is_monotonic_decreasing


def test_ev_arithmetic(con, frames):
    sc = _score(con, frames)
    ev = (
        sc.p_win * sc.expected_revenue * sc.expected_margin_pct
        - sc.estimating_hours * C.ESTIMATOR_RATE_PER_HOUR
    )
    assert np.allclose(ev, sc.expected_value)
    assert (sc.util_if_won >= sc.util_backlog - 1e-9).all()


def test_low_odds_are_a_pass(con, frames):
    sc = _score(con, frames)
    low = sc[sc.p_win < C.MIN_WIN_PROBABILITY]
    assert (low.recommendation == "Pass").all()
    assert low.reasons.str.contains("win odds").all()


def test_estimating_effort_fit_is_increasing_in_tons(con):
    fct = W.df(con, "select * from analytics.fct_bids")
    fit = S.fit_estimating_effort(fct)
    assert fit["b_log_tons"] > 0
    h = S.predict_estimating_hours(np.array([100.0, 400.0]), np.array([3.0, 3.0]), fit)
    assert h[1] > h[0]


def test_final_capacity_mart_builds_after_scoring(con, frames):
    sc = _score(con, frames)
    W.write_table(con, "pipeline_scorecard", sc)
    W.build_marts(con, "final")
    cap = W.df(con, "select * from analytics.mart_capacity_weekly")
    assert (cap.weighted_pipeline_tons >= 0).all()
    assert cap.weighted_pipeline_tons.sum() > 0
    assert np.allclose(
        cap.projected_utilisation, (cap.backlog_tons + cap.weighted_pipeline_tons) / cap.capacity_tons
    )
