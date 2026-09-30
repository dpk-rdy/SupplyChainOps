"""Semantic catalog: table and column descriptions from the dbt manifest, merged with the
warehouse's live column list. Rendered into the system prompt so Claude knows what each
mart means before it writes SQL."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from assistant.app.warehouse import TableInfo, Warehouse

log = logging.getLogger("assistant.catalog")


@dataclass
class CatalogTable:
    schema: str
    name: str
    description: str = ""
    columns: list[dict[str, str]] = field(default_factory=list)  # name, type, description
    row_count: int | None = None

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"


def load_manifest_descriptions(path: str) -> dict[str, dict]:
    """{table_name: {"description": str, "columns": {col: description}}} from dbt's manifest.json."""
    p = Path(path)
    if not p.exists():
        log.warning("dbt manifest not found at %s; descriptions will be empty (run `make dbt-docs`)", path)
        return {}
    manifest = json.loads(p.read_text())
    out: dict[str, dict] = {}
    for node in list(manifest.get("nodes", {}).values()) + list(manifest.get("sources", {}).values()):
        if node.get("resource_type") not in ("model", "seed", "source"):
            continue
        name = node.get("alias") or node.get("name")
        out[name] = {
            "description": (node.get("description") or "").strip(),
            "columns": {
                c: (meta.get("description") or "").strip() for c, meta in node.get("columns", {}).items()
            },
        }
    return out


def build_catalog(
    warehouse: Warehouse,
    manifest_path: str,
    include_prefixes: tuple[str, ...] = ("dim_", "fct_", "mart_", "forecast_"),
) -> list[CatalogTable]:
    docs = load_manifest_descriptions(manifest_path)
    tables: list[CatalogTable] = []
    for t in warehouse.list_tables():
        if not t.name.startswith(include_prefixes):
            continue
        try:
            info: TableInfo = warehouse.describe_table(t.schema, t.name)
        except Exception as exc:  # noqa: BLE001
            log.warning("skipping %s: %s", t.qualified, exc)
            continue
        doc = docs.get(t.name, {})
        cols = [
            {"name": c["name"], "type": c["type"], "description": doc.get("columns", {}).get(c["name"], "")}
            for c in info.columns
        ]
        tables.append(CatalogTable(t.schema, t.name, doc.get("description", ""), cols, info.row_count))
    return tables


def render_catalog(tables: list[CatalogTable], max_cols_per_table: int = 60) -> str:
    lines = []
    for t in tables:
        rows = f" ({t.row_count:,} rows)" if t.row_count is not None else ""
        lines.append(f"### {t.qualified}{rows}")
        if t.description:
            lines.append(t.description)
        for c in t.columns[:max_cols_per_table]:
            desc = f" - {c['description']}" if c["description"] else ""
            lines.append(f"- {c['name']} ({c['type']}){desc}")
        if len(t.columns) > max_cols_per_table:
            lines.append(f"- ... {len(t.columns) - max_cols_per_table} more columns (use describe_table)")
        lines.append("")
    return "\n".join(lines).strip()
