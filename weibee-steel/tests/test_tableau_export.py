import pandas as pd

from bid_intelligence import scorecard as S
from bid_intelligence import tableau_export as T
from bid_intelligence import warehouse as W
from bid_intelligence import win_model as M


def test_tableau_tables_reconcile(con, frames, tmp_path):
    fct = W.df(con, "select * from analytics.fct_bids")
    model = M.train(fct, cutoff=fct.bid_date.quantile(0.75))
    sc = S.score_pipeline(
        frames["pipeline"],
        fct,
        frames["customers"],
        W.df(con, "select * from analytics.mart_customer_scorecard"),
        W.df(con, "select * from analytics.mart_estimate_vs_actual"),
        W.df(con, "select * from analytics.mart_backlog_weekly"),
        model,
    )
    W.write_table(con, "pipeline_scorecard", sc)
    W.build_marts(con, "final")
    written = T.write(con, sc, tmp_path)
    sheets = pd.read_excel(written["xlsx"], sheet_name=None)
    assert set(sheets) == {
        "Bids and Jobs",
        "Customers",
        "Pipeline Scorecard",
        "Capacity Weekly",
        "Capacity Long",
    }
    b = sheets["Bids and Jobs"]
    assert len(b) == len(fct) and b["Won"].sum() == fct.is_won.sum()
    assert (b["Won Value"].sum() - fct.loc[fct.is_won == 1, "bid_price"].sum()) < 1
    assert b["Project Type"].notna().all() and not b["Project Type"].str.contains("_").any()
    assert len(sheets["Pipeline Scorecard"]) == len(sc)
    long = sheets["Capacity Long"]
    assert set(long["Load Type"]) == {"Backlog", "Weighted Pipeline", "Open Capacity"}
    if "hyper" in written:
        assert written["hyper"].stat().st_size > 0
