import csv
from pathlib import Path

import duckdb
import pytest

from ingestion import load_olist
from ingestion.olist_schema import SOURCE_TABLES


def _write_minimal_csvs(data_dir: Path) -> None:
    """Write one-row CSVs matching the Olist headers (leading-zero zip codes included)."""
    samples = {
        "olist_customers": ["c1", "u1", "01037", "sao paulo", "SP"],
        "olist_geolocation": ["01037", "-23.5", "-46.6", "sao paulo", "SP"],
        "olist_order_items": ["o1", "1", "p1", "s1", "2017-09-19 09:45:35", "58.90", "13.29"],
        "olist_order_payments": ["o1", "1", "credit_card", "1", "72.19"],
        "olist_order_reviews": ["r1", "o1", "5", "", "great", "2017-10-01 00:00:00", "2017-10-02 00:00:00"],
        "olist_orders": [
            "o1",
            "c1",
            "delivered",
            "2017-09-18 10:00:00",
            "2017-09-18 10:05:00",
            "2017-09-20 08:00:00",
            "2017-09-25 12:00:00",
            "2017-10-02 00:00:00",
        ],
        "olist_products": ["p1", "perfumaria", "40", "287", "1", "225", "16", "10", "14"],
        "olist_sellers": ["s1", "13023", "campinas", "SP"],
        "product_category_name_translation": ["perfumaria", "perfumery"],
    }
    for table in SOURCE_TABLES:
        with open(data_dir / table.filename, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([c for c, _ in table.columns])
            writer.writerow(samples[table.name])


def test_load_duckdb_keeps_types_and_leading_zeros(tmp_path: Path):
    _write_minimal_csvs(tmp_path)
    db = tmp_path / "wh.duckdb"
    counts = load_olist.load_duckdb(tmp_path, db)
    assert counts == {t.name: 1 for t in SOURCE_TABLES}

    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select customer_zip_code_prefix from raw.olist_customers").fetchone()[0] == "01037"
    types = dict(
        con.execute(
            "select column_name, data_type from information_schema.columns where table_schema='raw' and table_name='olist_orders'"
        ).fetchall()
    )
    assert types["order_purchase_timestamp"] == "TIMESTAMP"
    assert con.execute("select review_comment_title from raw.olist_order_reviews").fetchone()[0] is None
    con.close()


def test_validate_file_rejects_wrong_header(tmp_path: Path):
    bad = tmp_path / "olist_sellers_dataset.csv"
    bad.write_text("seller_id,wrong\n1,2\n")
    with pytest.raises(ValueError):
        load_olist._validate_file(SOURCE_TABLES[7], bad)
