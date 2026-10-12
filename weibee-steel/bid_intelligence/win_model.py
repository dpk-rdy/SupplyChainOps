"""Win-probability model: a regularised logistic regression in plain numpy.

Why not a gradient-boosted black box? With a few hundred historical bids, an interpretable model that
an estimator can argue with ("why does it think we lose podium work?") is worth more than a point of
AUC. The coefficients are reported in the model card, the evaluation is out-of-time (train on bids
before a cutoff, test on the ones after), and the fitted model is then refit on everything to score
the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from bid_intelligence import config as C

PRIOR_K = 3.0  # shrinkage weight for a customer's prior hit rate (pseudo-bids at the base rate)
TYPE_KEYS = [p.key for p in C.PROJECT_TYPES]
METHOD_KEYS = ["cmar", "negotiated", "design_build"]  # hard_bid is the reference level


# ------------------------------------------------------------------ features
def customer_prior_hit_rate(
    bids: pd.DataFrame, base_rate: float, as_of: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Time-aware relationship features: for each bid, that customer's decided bids and wins *before*
    this bid date, shrunk toward the base rate. No leakage from the bid's own outcome."""
    b = bids.sort_values(["bid_date", "bid_id"]).copy()
    prior_bids = np.zeros(len(b))
    prior_wins = np.zeros(len(b))
    seen: dict[str, list[int]] = {}
    for i, (cust, decided, won) in enumerate(
        zip(b["customer_id"], b["is_decided"], b["is_won"], strict=True)
    ):
        n = seen.setdefault(cust, [0, 0])
        prior_bids[i], prior_wins[i] = n
        if decided:
            n[0] += 1
            n[1] += int(won)
    b["gc_prior_bids"] = prior_bids
    b["gc_prior_hit_rate"] = (prior_wins + PRIOR_K * base_rate) / (prior_bids + PRIOR_K)
    return b[["bid_id", "gc_prior_bids", "gc_prior_hit_rate"]]


def customer_history_as_of(bids: pd.DataFrame, base_rate: float) -> pd.DataFrame:
    """Per-customer totals over the whole history (used to score future pipeline opportunities)."""
    g = (
        bids[bids.is_decided == 1]
        .groupby("customer_id")
        .agg(prior_bids=("is_won", "size"), prior_wins=("is_won", "sum"))
    )
    g["gc_prior_bids"] = g["prior_bids"].astype(float)
    g["gc_prior_hit_rate"] = (g["prior_wins"] + PRIOR_K * base_rate) / (g["prior_bids"] + PRIOR_K)
    return g[["gc_prior_bids", "gc_prior_hit_rate"]]


def design_matrix(frame: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    cols: dict[str, np.ndarray] = {
        "log_tons": np.log(frame["est_tons"].to_numpy(float)),
        "distance_100mi": frame["distance_miles"].to_numpy(float) / 100.0,
        "complexity": frame["complexity"].to_numpy(float),
        "markup_pct_x10": frame["markup_pct"].to_numpy(float) * 10.0,
        "num_bidders": frame["num_bidders"].to_numpy(float),
        "gc_prior_hit_rate": frame["gc_prior_hit_rate"].to_numpy(float),
        "log1p_gc_prior_bids": np.log1p(frame["gc_prior_bids"].to_numpy(float)),
        "fab_and_erect": (frame["scope"] == "fab_erect").to_numpy(float),
    }
    for m in METHOD_KEYS:
        cols[f"method={m}"] = (frame["delivery_method"] == m).to_numpy(float)
    for t in TYPE_KEYS[1:]:  # first type (warehouse) is the reference level
        cols[f"type={t}"] = (frame["project_type"] == t).to_numpy(float)
    names = list(cols)
    return np.column_stack([cols[n] for n in names]), names


# ------------------------------------------------------------------ model
@dataclass
class LogisticModel:
    names: list[str]
    mean: np.ndarray
    scale: np.ndarray
    weights: np.ndarray  # standardised-space coefficients, intercept last
    l2: float = 1.0
    diagnostics: dict = field(default_factory=dict)

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        z = (x - self.mean) / self.scale
        return 1.0 / (1.0 + np.exp(-(z @ self.weights[:-1] + self.weights[-1])))

    def coefficients(self) -> pd.DataFrame:
        """Standardised coefficients: effect on the log-odds of one standard deviation of each feature."""
        return (
            pd.DataFrame({"feature": self.names, "coef_std": self.weights[:-1]})
            .assign(abs_coef=lambda d: d.coef_std.abs())
            .sort_values("abs_coef", ascending=False)
            .drop(columns="abs_coef")
            .reset_index(drop=True)
        )


def fit_logistic(
    x: np.ndarray, y: np.ndarray, names: list[str], l2: float = 1.0, iters: int = 400
) -> LogisticModel:
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale == 0] = 1.0
    z = np.column_stack([(x - mean) / scale, np.ones(len(x))])
    w = np.zeros(z.shape[1])
    reg = np.full(z.shape[1], l2)
    reg[-1] = 0.0  # never shrink the intercept
    for _ in range(iters):  # Newton's method with ridge penalty; converges in a handful of steps
        p = 1.0 / (1.0 + np.exp(-(z @ w)))
        grad = z.T @ (p - y) + reg * w
        hess = (z.T * (p * (1 - p))) @ z + np.diag(reg)
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return LogisticModel(names=names, mean=mean, scale=scale, weights=w, l2=l2)


# ------------------------------------------------------------------ evaluation
def auc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    # average ranks for ties
    for v in np.unique(p):
        m = p == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    n_pos, n_neg = y.sum(), (1 - y).sum()
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def calibration_table(y: np.ndarray, p: np.ndarray, bins: int = 5) -> pd.DataFrame:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[-1] += 1e-9
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    rows = []
    for k in range(bins):
        m = idx == k
        if m.sum() == 0:
            continue
        rows.append(
            {
                "bin": k + 1,
                "bids": int(m.sum()),
                "predicted": float(p[m].mean()),
                "observed": float(y[m].mean()),
            }
        )
    return pd.DataFrame(rows)


def evaluate(y: np.ndarray, p: np.ndarray, base_rate: float) -> dict:
    eps = 1e-9
    ll = -np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
    ll0 = -np.mean(y * np.log(base_rate + eps) + (1 - y) * np.log(1 - base_rate + eps))
    return {
        "n": int(len(y)),
        "base_rate": float(y.mean()),
        "auc": auc(y, p),
        "brier": float(np.mean((p - y) ** 2)),
        "brier_baseline": float(np.mean((base_rate - y) ** 2)),
        "log_loss": float(ll),
        "log_loss_baseline": float(ll0),
        "calibration": calibration_table(y, p).to_dict(orient="records"),
    }


# ------------------------------------------------------------------ orchestration
def prepare_training_frame(fct_bids: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    decided = fct_bids[fct_bids.is_decided == 1].copy()
    base_rate = float(decided.is_won.mean())
    prior = customer_prior_hit_rate(fct_bids, base_rate)
    decided = (
        decided.merge(prior, on="bid_id", how="left")
        .sort_values(["bid_date", "bid_id"])
        .reset_index(drop=True)
    )
    return decided, base_rate


def train(
    fct_bids: pd.DataFrame, cutoff: str | pd.Timestamp = "2025-07-01", l2: float = 1.0
) -> LogisticModel:
    frame, base_rate = prepare_training_frame(fct_bids)
    x, names = design_matrix(frame)
    y = frame.is_won.to_numpy(float)
    cutoff = pd.Timestamp(cutoff)
    train_mask = (frame.bid_date < cutoff).to_numpy()
    holdout = fit_logistic(x[train_mask], y[train_mask], names, l2=l2)
    p_test = holdout.predict_proba(x[~train_mask])
    p_train = holdout.predict_proba(x[train_mask])
    final = fit_logistic(x, y, names, l2=l2)
    final.diagnostics = {
        "cutoff": str(cutoff.date()),
        "train": evaluate(y[train_mask], p_train, base_rate=float(y[train_mask].mean())),
        "test": evaluate(y[~train_mask], p_test, base_rate=float(y[train_mask].mean())),
        "base_rate_all": base_rate,
        "l2": l2,
        "features": names,
    }
    return final
