"""Download the Olist dataset and load it into the raw layer of the warehouse.

Usage:
    python -m ingestion.load_olist download [--data-dir data/raw]
    python -m ingestion.load_olist load --backend duckdb  [--duckdb-path ...]
    python -m ingestion.load_olist load --backend bigquery --project ... --dataset raw_olist

The download step prefers the official Kaggle release (needs the `kaggle` CLI
and credentials) and falls back to public GitHub mirrors of the same files.
The load step is idempotent: every raw table is replaced on each run.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from ingestion.olist_schema import KAGGLE_DATASET, MIRRORS, SOURCE_TABLES, TYPE_MAP, SourceTable

log = logging.getLogger("ingestion")

DEFAULT_DATA_DIR = Path("data/raw")
DEFAULT_DUCKDB_PATH = Path("data/warehouse/supplychainops.duckdb")
RAW_SCHEMA = "raw"


# --------------------------------------------------------------------------- download
def _kaggle_available() -> bool:
    has_creds = (Path.home() / ".kaggle" / "kaggle.json").exists() or (
        os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")
    )
    return bool(has_creds and shutil.which("kaggle"))


def download(data_dir: Path, force: bool = False) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    missing = [t for t in SOURCE_TABLES if force or not (data_dir / t.filename).exists()]
    if not missing:
        log.info("all %d source files already present in %s", len(SOURCE_TABLES), data_dir)
        return

    if _kaggle_available():
        log.info("downloading %s with the Kaggle CLI", KAGGLE_DATASET)
        subprocess.run(
            ["kaggle", "datasets", "download", "-d", KAGGLE_DATASET, "-p", str(data_dir), "--unzip"],
            check=True,
        )
    else:
        log.info("Kaggle CLI not configured; using public mirrors")
        for table in missing:
            _download_from_mirrors(table, data_dir)

    for table in SOURCE_TABLES:
        _validate_file(table, data_dir / table.filename)


def _download_from_mirrors(table: SourceTable, data_dir: Path) -> None:
    dest = data_dir / table.filename
    last_error: Exception | None = None
    for mirror in MIRRORS:
        url = mirror.format(filename=table.filename)
        try:
            log.info("  %s <- %s", table.filename, url)
            with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            return
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            last_error = exc
            log.warning("  mirror failed (%s); trying next", exc)
    raise RuntimeError(f"could not download {table.filename} from any mirror") from last_error


def _validate_file(table: SourceTable, path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh))
    expected = [c for c, _ in table.columns]
    if header != expected:
        raise ValueError(f"{path.name}: header {header} != expected {expected}")
    if table.expected_rows is not None:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = sum(1 for _ in csv.reader(fh)) - 1
        if rows != table.expected_rows:
            log.warning("%s: %d rows (Kaggle release has %d)", path.name, rows, table.expected_rows)


# --------------------------------------------------------------------------- duckdb
def load_duckdb(data_dir: Path, duckdb_path: Path, schema: str = RAW_SCHEMA) -> dict[str, int]:
    import duckdb

    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(duckdb_path))
    counts: dict[str, int] = {}
    try:
        con.execute(f"create schema if not exists {schema}")
        for table in SOURCE_TABLES:
            path = data_dir / table.filename
            columns = ", ".join(f"'{c}': '{TYPE_MAP[t][0]}'" for c, t in table.columns)
            con.execute(
                f"""
                create or replace table {schema}.{table.name} as
                select * from read_csv(
                    '{path.as_posix()}',
                    header = true,
                    columns = {{{columns}}},
                    timestampformat = '%Y-%m-%d %H:%M:%S',
                    nullstr = ''
                )
                """
            )
            counts[table.name] = con.execute(f"select count(*) from {schema}.{table.name}").fetchone()[0]
            log.info("  %s.%s: %d rows", schema, table.name, counts[table.name])
    finally:
        con.close()
    return counts


# --------------------------------------------------------------------------- bigquery
def load_bigquery(data_dir: Path, project: str, dataset: str, location: str = "US") -> dict[str, int]:
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    ds_ref = bigquery.Dataset(f"{project}.{dataset}")
    ds_ref.location = location
    client.create_dataset(ds_ref, exists_ok=True)

    counts: dict[str, int] = {}
    for table in SOURCE_TABLES:
        schema = [bigquery.SchemaField(c, TYPE_MAP[t][1]) for c, t in table.columns]
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            schema=schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            allow_quoted_newlines=True,  # review comments contain newlines
            null_marker="",
        )
        table_id = f"{project}.{dataset}.{table.name}"
        with open(data_dir / table.filename, "rb") as fh:
            job = client.load_table_from_file(fh, table_id, job_config=job_config)
        job.result()
        counts[table.name] = client.get_table(table_id).num_rows
        log.info("  %s: %d rows", table_id, counts[table.name])
    return counts


# --------------------------------------------------------------------------- cli
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_dl = sub.add_parser("download", help="download the Olist CSVs")
    p_dl.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    p_dl.add_argument("--force", action="store_true")

    p_load = sub.add_parser("load", help="load CSVs into the raw warehouse layer")
    p_load.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    p_load.add_argument(
        "--backend", choices=["duckdb", "bigquery"], default=os.environ.get("WAREHOUSE_BACKEND", "duckdb")
    )
    p_load.add_argument(
        "--duckdb-path", type=Path, default=Path(os.environ.get("DUCKDB_PATH", DEFAULT_DUCKDB_PATH))
    )
    p_load.add_argument("--project", default=os.environ.get("GCP_PROJECT"))
    p_load.add_argument("--dataset", default=os.environ.get("BQ_DATASET_RAW", "raw_olist"))
    p_load.add_argument("--location", default=os.environ.get("BQ_LOCATION", "US"))

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.command == "download":
        download(args.data_dir, force=args.force)
        return 0

    for table in SOURCE_TABLES:
        _validate_file(table, args.data_dir / table.filename)
    if args.backend == "duckdb":
        load_duckdb(args.data_dir, args.duckdb_path)
    else:
        if not args.project:
            parser.error("--project (or GCP_PROJECT) is required for the bigquery backend")
        load_bigquery(args.data_dir, args.project, args.dataset, args.location)
    return 0


if __name__ == "__main__":
    sys.exit(main())
