import numpy as np
import pandas as pd

from bid_intelligence import warehouse as W
from bid_intelligence import win_model as M


def test_auc_matches_known_values():
    y = np.array([0, 0, 1, 1])
    assert M.auc(y, np.array([0.1, 0.4, 0.35, 0.8])) == 0.75
    assert M.auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 0.0


def test_customer_prior_hit_rate_has_no_leakage():
    bids = pd.DataFrame(
        {
            "bid_id": ["b1", "b2", "b3"],
            "customer_id": ["g", "g", "g"],
            "bid_date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
            "is_decided": [1, 1, 1],
            "is_won": [1, 0, 1],
        }
    )
    out = M.customer_prior_hit_rate(bids, base_rate=0.3).set_index("bid_id")
    assert out.loc["b1", "gc_prior_bids"] == 0 and out.loc["b1", "gc_prior_hit_rate"] == 0.3
    assert out.loc["b2", "gc_prior_bids"] == 1 and out.loc["b2", "gc_prior_hit_rate"] > 0.3
    assert out.loc["b3", "gc_prior_bids"] == 2


def test_logistic_recovers_a_separable_signal():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(400, 2))
    y = (x[:, 0] + 0.8 * rng.normal(size=400) > 0).astype(float)
    m = M.fit_logistic(x, y, ["a", "b"], l2=0.1)
    coefs = m.coefficients().set_index("feature").coef_std
    assert coefs["a"] > 1.0 and abs(coefs["b"]) < 0.25 * coefs["a"]
    assert M.auc(y, m.predict_proba(x)) > 0.85


def test_train_beats_base_rate_out_of_time(con):
    fct = W.df(con, "select * from analytics.fct_bids")
    model = M.train(fct, cutoff=fct.bid_date.quantile(0.75))
    t = model.diagnostics["test"]
    assert t["n"] > 30
    assert t["auc"] > 0.55
    assert t["brier"] < t["brier_baseline"] + 0.01
    assert (model.predict_proba(M.design_matrix(M.prepare_training_frame(fct)[0])[0]) < 1).all()
