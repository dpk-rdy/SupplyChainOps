"""DuckDB warehouse: load the raw tables, build the analytics marts from the SQL files in ``sql/``.

The SQL is plain ANSI-ish DuckDB and would port to BigQuery or Postgres with small changes; the
point is that every number in the report traces back to one of these files.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

SQL_DIR = Path(__file__).parent / "sql"


def connect(path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(path) if path else ":memory:")
    con.execute("create schema if not exists raw")
    con.execute("create schema if not exists analytics")
    return con


def load_raw(con: duckdb.DuckDBPyConnection, frames: dict[str, pd.DataFrame]) -> None:
    for name, frame in frames.items():
        if name.startswith("_"):
            continue
        con.register("_tmp", frame)
        con.execute(f"create or replace table raw.{name} as select * from _tmp")
        con.unregister("_tmp")


def sql_files(stage: str) -> list[Path]:
    """``base`` marts are everything before the scorecard; ``final`` marts (9x_) need it."""
    files = sorted(SQL_DIR.glob("*.sql"))
    if stage == "base":
        return [f for f in files if not f.name.startswith("9")]
    if stage == "final":
        return [f for f in files if f.name.startswith("9")]
    raise ValueError(stage)


def build_marts(con: duckdb.DuckDBPyConnection, stage: str = "base") -> list[str]:
    built = []
    for f in sql_files(stage):
        con.execute(f.read_text())
        built.append(f.stem)
    return built


def df(con: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


def write_table(
    con: duckdb.DuckDBPyConnection, name: str, frame: pd.DataFrame, schema: str = "analytics"
) -> None:
    con.register("_tmp", frame)
    con.execute(f"create or replace table {schema}.{name} as select * from _tmp")
    con.unregister("_tmp")
