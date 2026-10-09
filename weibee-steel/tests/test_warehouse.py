import pytest

from bid_intelligence import warehouse as W


def test_fct_bids_reconciles_to_raw(con):
    raw = W.df(con, "select count(*) n, sum(bid_price) v from raw.bids").iloc[0]
    fct = W.df(con, "select count(*) n, sum(bid_price) v from analytics.fct_bids").iloc[0]
    assert raw.n == fct.n and abs(raw.v - fct.v) < 1


def test_hit_rates_are_ratios_of_sums(con):
    d = W.df(con, "select * from analytics.mart_hit_rate_by_dimension")
    assert ((d.hit_rate_count >= 0) & (d.hit_rate_count <= 1)).all()
    assert (d.bids_won <= d.bids_decided).all()
    # each dimension partitions the same bid set
    totals = d.groupby("dimension").bids_submitted.sum()
    assert totals.nunique() == 1


def test_quarterly_sums_match_fct(con):
    q = W.df(
        con, "select sum(bids_won) w, sum(bids_decided) d from analytics.mart_bid_results_quarterly"
    ).iloc[0]
    f = W.df(con, "select sum(is_won) w, sum(is_decided) d from analytics.fct_bids").iloc[0]
    assert q.w == f.w and q.d == f.d


def test_margin_slip_is_estimate_minus_actual(con):
    j = W.df(
        con,
        "select est_gross_margin_pct e, actual_gross_margin_pct a, margin_slip_pts s from analytics.fct_jobs where status = 'complete'",
    )
    assert ((j.e - j.a - j.s).abs() < 1e-9).all()


def test_estimate_vs_actual_all_row_is_dollar_weighted(con):
    allrow = W.df(con, "select * from analytics.mart_estimate_vs_actual where dimension = 'all'").iloc[0]
    j = W.df(
        con,
        "select sum(final_revenue - actual_direct_cost) / sum(final_revenue) m, count(*) n from analytics.fct_jobs where status = 'complete'",
    ).iloc[0]
    assert abs(allrow.actual_gross_margin_pct - j.m) < 1e-9 and allrow.jobs_complete == j.n


def test_backlog_conserves_tonnage(con):
    """Spreading each job over its window must add back up to the jobs' tonnage inside the capacity calendar."""
    spread = W.df(con, "select sum(backlog_tons) t from analytics.mart_backlog_weekly").iloc[0].t
    direct = (
        W.df(
            con,
            """select sum(o.est_tons) t from raw.jobs j join raw.opportunities o using (opportunity_id)
           where j.fab_end_week <= (select max(week_start) from raw.capacity)""",
        )
        .iloc[0]
        .t
    )
    assert spread == pytest.approx(direct, rel=0.02)


def test_customer_classes_are_assigned(con):
    c = W.df(con, "select relationship_class, count(*) n from analytics.mart_customer_scorecard group by 1")
    assert set(c.relationship_class) <= {"A", "B", "C", "New / thin"}
    assert c.n.sum() == W.df(con, "select count(*) n from raw.customers").iloc[0].n
