"""Canonical schema for the nine Olist source files.

Column types are declared explicitly (rather than inferred) so that zip-code
prefixes keep their leading zeros and both DuckDB and BigQuery load the same
shapes. Types use a small portable vocabulary that each loader maps onto its
warehouse.
"""

from __future__ import annotations

from dataclasses import dataclass

# Portable type names -> (duckdb type, bigquery type)
TYPE_MAP: dict[str, tuple[str, str]] = {
    "string": ("VARCHAR", "STRING"),
    "int": ("BIGINT", "INT64"),
    "float": ("DOUBLE", "FLOAT64"),
    "timestamp": ("TIMESTAMP", "TIMESTAMP"),
}


@dataclass(frozen=True)
class SourceTable:
    name: str  # table name in the raw schema
    filename: str  # CSV filename inside the Olist archive
    columns: tuple[tuple[str, str], ...]  # (column, portable type)
    expected_rows: int | None = None  # row count in the Kaggle release (sanity check)


SOURCE_TABLES: tuple[SourceTable, ...] = (
    SourceTable(
        "olist_customers",
        "olist_customers_dataset.csv",
        (
            ("customer_id", "string"),
            ("customer_unique_id", "string"),
            ("customer_zip_code_prefix", "string"),
            ("customer_city", "string"),
            ("customer_state", "string"),
        ),
        99_441,
    ),
    SourceTable(
        "olist_geolocation",
        "olist_geolocation_dataset.csv",
        (
            ("geolocation_zip_code_prefix", "string"),
            ("geolocation_lat", "float"),
            ("geolocation_lng", "float"),
            ("geolocation_city", "string"),
            ("geolocation_state", "string"),
        ),
        1_000_163,
    ),
    SourceTable(
        "olist_order_items",
        "olist_order_items_dataset.csv",
        (
            ("order_id", "string"),
            ("order_item_id", "int"),
            ("product_id", "string"),
            ("seller_id", "string"),
            ("shipping_limit_date", "timestamp"),
            ("price", "float"),
            ("freight_value", "float"),
        ),
        112_650,
    ),
    SourceTable(
        "olist_order_payments",
        "olist_order_payments_dataset.csv",
        (
            ("order_id", "string"),
            ("payment_sequential", "int"),
            ("payment_type", "string"),
            ("payment_installments", "int"),
            ("payment_value", "float"),
        ),
        103_886,
    ),
    SourceTable(
        "olist_order_reviews",
        "olist_order_reviews_dataset.csv",
        (
            ("review_id", "string"),
            ("order_id", "string"),
            ("review_score", "int"),
            ("review_comment_title", "string"),
            ("review_comment_message", "string"),
            ("review_creation_date", "timestamp"),
            ("review_answer_timestamp", "timestamp"),
        ),
        100_000,
    ),
    SourceTable(
        "olist_orders",
        "olist_orders_dataset.csv",
        (
            ("order_id", "string"),
            ("customer_id", "string"),
            ("order_status", "string"),
            ("order_purchase_timestamp", "timestamp"),
            ("order_approved_at", "timestamp"),
            ("order_delivered_carrier_date", "timestamp"),
            ("order_delivered_customer_date", "timestamp"),
            ("order_estimated_delivery_date", "timestamp"),
        ),
        99_441,
    ),
    SourceTable(
        "olist_products",
        "olist_products_dataset.csv",
        (
            ("product_id", "string"),
            ("product_category_name", "string"),
            ("product_name_lenght", "int"),
            ("product_description_lenght", "int"),
            ("product_photos_qty", "int"),
            ("product_weight_g", "float"),
            ("product_length_cm", "float"),
            ("product_height_cm", "float"),
            ("product_width_cm", "float"),
        ),
        32_951,
    ),
    SourceTable(
        "olist_sellers",
        "olist_sellers_dataset.csv",
        (
            ("seller_id", "string"),
            ("seller_zip_code_prefix", "string"),
            ("seller_city", "string"),
            ("seller_state", "string"),
        ),
        3_095,
    ),
    SourceTable(
        "product_category_name_translation",
        "product_category_name_translation.csv",
        (
            ("product_category_name", "string"),
            ("product_category_name_english", "string"),
        ),
        71,
    ),
)

# Public mirrors of the Kaggle release, tried in order when the Kaggle CLI is
# not configured. Both hold byte-identical copies of the Kaggle CSVs.
MIRRORS: tuple[str, ...] = (
    "https://raw.githubusercontent.com/dujiaying/olist/master/data/{filename}",
    "https://raw.githubusercontent.com/Ganesh7699/Brazilian-E-Commerce-OList/main/{filename}",
)

KAGGLE_DATASET = "olistbr/brazilian-ecommerce"
