"""Read dbt marts from, and write forecast tables to, DuckDB or BigQuery."""

from __future__ import annotations

import logging
from typing import Protocol

import pandas as pd

log = logging.getLogger("forecasting")


class Warehouse(Protocol):
    def read_table(self, schema: str, table: str) -> pd.DataFrame: ...

    def append(self, schema: str, table: str, frame: pd.DataFrame) -> None: ...


class DuckDBWarehouse:
    def __init__(self, path: str):
        import duckdb

        self.con = duckdb.connect(path)

    def read_table(self, schema: str, table: str) -> pd.DataFrame:
        return self.con.execute(f"select * from {schema}.{table}").df()

    def append(self, schema: str, table: str, frame: pd.DataFrame) -> None:
        self.con.execute(f"create schema if not exists {schema}")
        self.con.register("_incoming", frame)
        self.con.execute(f"create table if not exists {schema}.{table} as select * from _incoming limit 0")
        self.con.execute(f"insert into {schema}.{table} select * from _incoming")
        self.con.unregister("_incoming")
        log.info("wrote %d rows to %s.%s", len(frame), schema, table)

    def close(self) -> None:
        self.con.close()


class BigQueryWarehouse:
    def __init__(self, project: str, location: str = "US"):
        from google.cloud import bigquery

        self.bq = bigquery
        self.client = bigquery.Client(project=project)
        self.project = project
        self.location = location

    def read_table(self, schema: str, table: str) -> pd.DataFrame:
        return self.client.query(f"select * from `{self.project}.{schema}.{table}`").to_dataframe()

    def append(self, schema: str, table: str, frame: pd.DataFrame) -> None:
        ds = self.bq.Dataset(f"{self.project}.{schema}")
        ds.location = self.location
        self.client.create_dataset(ds, exists_ok=True)
        job = self.client.load_table_from_dataframe(
            frame,
            f"{self.project}.{schema}.{table}",
            job_config=self.bq.LoadJobConfig(write_disposition=self.bq.WriteDisposition.WRITE_APPEND),
        )
        job.result()
        log.info("wrote %d rows to %s.%s.%s", len(frame), self.project, schema, table)

    def close(self) -> None:
        self.client.close()


def connect(backend: str, duckdb_path: str, gcp_project: str | None, location: str = "US"):
    if backend == "bigquery":
        if not gcp_project:
            raise ValueError("GCP_PROJECT is required for the bigquery backend")
        return BigQueryWarehouse(gcp_project, location)
    return DuckDBWarehouse(duckdb_path)
