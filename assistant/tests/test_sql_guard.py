import pytest

from assistant.app import sql_guard as g

ALLOWED = {"analytics.fct_orders", "analytics.mart_kpi_daily_region", "forecasts.forecast_runs"}


def test_accepts_select_and_wraps_with_limit():
    out = g.validate("select customer_state, count(*) from analytics.fct_orders group by 1", ALLOWED, 50)
    assert out.executable.startswith("select * from (") and out.executable.endswith("limit 51")
    assert out.referenced_tables == ("analytics.fct_orders",)


def test_unqualified_table_resolves_to_analytics():
    out = g.validate("SELECT count(*) FROM fct_orders", ALLOWED, 10)
    assert out.referenced_tables == ("analytics.fct_orders",)


def test_cte_names_are_not_treated_as_tables():
    sql = "with base as (select * from analytics.fct_orders), agg as (select count(*) n from base) select n from agg"
    out = g.validate(sql, ALLOWED, 10)
    assert out.referenced_tables == ("analytics.fct_orders",)


def test_bigquery_three_part_names_are_allowed():
    out = g.validate("select 1 from `my-proj.analytics.fct_orders`", ALLOWED, 10)
    assert out.referenced_tables == ("analytics.fct_orders",)


@pytest.mark.parametrize(
    "sql, message",
    [
        ("insert into analytics.fct_orders values (1)", "SELECT / WITH"),
        ("select 1 from analytics.fct_orders; drop table analytics.fct_orders", "single statement"),
        (
            "select * from analytics.fct_orders where 1=1 union all select * from raw.olist_orders",
            "not in the allowed",
        ),
        ("select * from read_csv_auto('/etc/passwd')", "forbidden function"),
        ("select * from 'data/raw/olist_orders_dataset.csv'", "not allowed"),
        ("with x as (delete from analytics.fct_orders) select 1 from x", "forbidden keyword"),
        ("select * from information_schema.tables", "not in the allowed"),
        ("select 1", "at least one warehouse table"),
        ("", "empty"),
    ],
)
def test_rejections(sql, message):
    with pytest.raises(g.SQLGuardError, match=message):
        g.validate(sql, ALLOWED, 10)


def test_keywords_inside_identifiers_and_strings_are_fine():
    sql = "select count(*) from analytics.fct_orders where order_status = 'created' and created_at_offset is null"
    assert g.validate(sql, ALLOWED, 10).referenced_tables == ("analytics.fct_orders",)


def test_normalise_ignores_case_whitespace_comments_and_semicolon():
    a = "SELECT   count(*)\n FROM analytics.fct_orders -- all orders\n;"
    b = "select count(*) from analytics.fct_orders"
    assert g.normalise(a) == g.normalise(b)
