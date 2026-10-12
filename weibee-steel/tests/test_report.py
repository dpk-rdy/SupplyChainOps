from bid_intelligence import __main__ as cli
from bid_intelligence import charts


def test_chart_helpers_return_svg():
    assert "<svg" in charts.hbar([{"label": "a", "value": 0.4}, {"label": "b", "value": 0.2}])
    assert "<svg" in charts.dumbbell([{"label": "a", "a": 0.2, "b": 0.1}], 0, 0.3)
    assert "<svg" in charts.vbar(["x", "y"], [1, 2])
    assert "<svg" in charts.line_chart(["q1", "q2"], [("s", charts.BLUE, [0.1, 0.2])])
    assert "<svg" in charts.stacked_area(
        ["w1", "w2"], [("a", charts.BLUE, [1, 2])], line=("cap", "#000", [3, 3])
    )
    assert charts.fmt_money(1_250_000) == "$1.2M" and charts.fmt_pct(0.256) == "26%"


def test_end_to_end_run_writes_report(tmp_path):
    ctx = cli.run(seed=11, out=tmp_path)
    html = (tmp_path / "bid_intelligence_report.html").read_text()
    for anchor in ("id='findings'", "id='scorecard'", "id='model'", "id='capacity'"):
        assert anchor in html
    assert (tmp_path / "pipeline_scorecard.csv").exists() and (tmp_path / "model_card.json").exists()
    assert len(ctx["insights"]) >= 5
    assert "synthetic" in html.lower()
