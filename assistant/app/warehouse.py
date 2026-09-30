"""Read-only warehouse adapters used by the assistant's tools."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger("assistant.warehouse")


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int
    bytes_processed: int | None = None


@dataclass
class TableInfo:
    schema: str
    name: str
    columns: list[dict[str, str]] = field(default_factory=list)  # {name, type}
    row_count: int | None = None

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"


class Warehouse(Protocol):
    dialect: str

    def list_tables(self) -> list[TableInfo]: ...

    def describe_table(self, schema: str, name: str) -> TableInfo: ...

    def query(self, sql: str, max_rows: int, timeout_seconds: int) -> QueryResult: ...


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    try:
        import decimal

        if isinstance(value, decimal.Decimal):
            return float(value)
    except ImportError:  # pragma: no cover
        pass
    return value


class DuckDBWarehouse:
    """DuckDB opened read-only; one connection guarded by a lock (DuckDB connections are not thread-safe)."""

    dialect = "duckdb"

    def __init__(self, path: str, schemas: tuple[str, ...] = ("analytics", "forecasts")):
        import duckdb

        self.con = duckdb.connect(path, read_only=True)
        self.schemas = schemas
        self._lock = threading.Lock()

    def list_tables(self) -> list[TableInfo]:
        placeholders = ", ".join("?" for _ in self.schemas)
        with self._lock:
            rows = self.con.execute(
                f"select table_schema, table_name from information_schema.tables where table_schema in ({placeholders}) order by 1, 2",
                list(self.schemas),
            ).fetchall()
        return [TableInfo(schema=s, name=n) for s, n in rows]

    def describe_table(self, schema: str, name: str) -> TableInfo:
        with self._lock:
            cols = self.con.execute(
                "select column_name, data_type from information_schema.columns where table_schema = ? and table_name = ? order by ordinal_position",
                [schema, name],
            ).fetchall()
            if not cols:
                raise KeyError(f"{schema}.{name} not found")
            count = self.con.execute(f"select count(*) from {schema}.{name}").fetchone()[0]
        return TableInfo(
            schema=schema, name=name, columns=[{"name": c, "type": t} for c, t in cols], row_count=count
        )

    def query(self, sql: str, max_rows: int, timeout_seconds: int) -> QueryResult:  # noqa: ARG002 - DuckDB has no per-query timeout
        start = time.perf_counter()
        with self._lock:
            cur = self.con.execute(sql)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        return QueryResult(
            columns=columns,
            rows=[[_jsonable(v) for v in r] for r in rows],
            row_count=len(rows),
            truncated=truncated,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
        )


class BigQueryWarehouse:
    dialect = "bigquery"

    def __init__(
        self,
        project: str,
        datasets: tuple[str, ...] = ("analytics", "forecasts"),
        location: str = "US",
        maximum_bytes_billed: int = 2_000_000_000,
    ):
        from google.cloud import bigquery

        self.bq = bigquery
        self.client = bigquery.Client(project=project, location=location)
        self.project = project
        self.datasets = datasets
        self.maximum_bytes_billed = maximum_bytes_billed

    def list_tables(self) -> list[TableInfo]:
        out = []
        for ds in self.datasets:
            try:
                for t in self.client.list_tables(f"{self.project}.{ds}"):
                    out.append(TableInfo(schema=ds, name=t.table_id))
            except Exception as exc:  # noqa: BLE001 - a missing dataset (e.g. forecasts) is not fatal
                log.warning("could not list %s: %s", ds, exc)
        return out

    def describe_table(self, schema: str, name: str) -> TableInfo:
        table = self.client.get_table(f"{self.project}.{schema}.{name}")
        return TableInfo(
            schema=schema,
            name=name,
            columns=[{"name": f.name, "type": f.field_type} for f in table.schema],
            row_count=table.num_rows,
        )

    def _qualify(self, sql: str) -> str:
        # dataset.table -> `project.dataset.table` so the same SQL works on both backends
        import re

        for ds in self.datasets:
            sql = re.sub(rf"(?<![\w.`]){ds}\.([a-zA-Z_]\w*)", rf"`{self.project}.{ds}.\1`", sql)
        return sql

    def query(self, sql: str, max_rows: int, timeout_seconds: int) -> QueryResult:
        start = time.perf_counter()
        config = self.bq.QueryJobConfig(use_legacy_sql=False, maximum_bytes_billed=self.maximum_bytes_billed)
        job = self.client.query(self._qualify(sql), job_config=config)
        iterator = job.result(timeout=timeout_seconds, max_results=max_rows + 1)
        columns = [f.name for f in iterator.schema]
        rows = [[_jsonable(v) for v in row.values()] for row in iterator]
        truncated = len(rows) > max_rows
        return QueryResult(
            columns=columns,
            rows=rows[:max_rows],
            row_count=min(len(rows), max_rows),
            truncated=truncated,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
            bytes_processed=job.total_bytes_processed,
        )


def connect(settings) -> Warehouse:
    schemas = (settings.analytics_schema, settings.forecast_schema)
    if settings.warehouse_backend == "bigquery":
        if not settings.gcp_project:
            raise ValueError("GCP_PROJECT is required for the bigquery backend")
        return BigQueryWarehouse(
            settings.gcp_project, schemas, settings.bq_location, settings.bq_maximum_bytes_billed
        )
    return DuckDBWarehouse(settings.duckdb_path, schemas)
