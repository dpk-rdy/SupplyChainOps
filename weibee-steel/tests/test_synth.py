import numpy as np
import pandas as pd

from bid_intelligence import synth


def test_generation_is_deterministic():
    a = synth.generate(seed=3, n_opportunities=120, n_pipeline=10)
    b = synth.generate(seed=3, n_opportunities=120, n_pipeline=10)
    for k in a:
        pd.testing.assert_frame_equal(a[k], b[k])


def test_tables_and_keys(frames):
    bids, opps, jobs, pipe = frames["bids"], frames["opportunities"], frames["jobs"], frames["pipeline"]
    assert bids.bid_id.is_unique and opps.opportunity_id.is_unique and jobs.job_id.is_unique
    assert set(bids.opportunity_id) <= set(opps.opportunity_id)
    assert set(jobs.opportunity_id) == set(bids[bids.result == "won"].opportunity_id)
    assert set(bids.result) <= {"won", "lost", "cancelled", "pending"}
    assert (opps[opps.decision == "no_bid"].opportunity_id.isin(bids.opportunity_id) == False).all()  # noqa: E712
    assert pipe.opportunity_id.str.startswith("P-").all()


def test_economics_are_sane(frames):
    bids, jobs = frames["bids"], frames["jobs"]
    ppt = (
        bids.bid_price
        / frames["opportunities"].set_index("opportunity_id").loc[bids.opportunity_id, "est_tons"].to_numpy()
    )
    assert 2_500 < ppt.median() < 9_000  # $/ton fab + erect
    assert 0.15 < (bids.result == "won").mean() < 0.45
    done = jobs[jobs.status == "complete"]
    gm = (done.final_revenue - done.actual_direct_cost) / done.final_revenue
    assert 0.05 < gm.median() < 0.35
    lost_price = bids[(bids.result == "lost") & (bids.lost_reason == "price")]
    gap = (lost_price.bid_price - lost_price.competitor_low_price) / lost_price.bid_price
    assert gap.dropna().between(0, 0.3).all()


def test_pending_results_have_no_outcome(frames):
    pend = frames["bids"][frames["bids"].result == "pending"]
    assert pend.result_date.isna().all() and pend.lost_reason.isna().all()


def test_planted_structure_is_recoverable(frames):
    """Relationship GCs and better-fit types should win more often in the generated history."""
    bids = frames["bids"].merge(frames["opportunities"], on="opportunity_id")
    decided = bids[bids.result.isin(["won", "lost"])]
    by_type = decided.groupby("project_type").result.apply(lambda s: (s == "won").mean())
    assert by_type["warehouse"] > by_type["healthcare"]
    assert np.isfinite(frames["_truth"].p_win_true).all()
