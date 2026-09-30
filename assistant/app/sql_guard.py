"""Static guardrails applied to every SQL statement the model asks to run.

The warehouse connection is already read-only; this layer makes the contract explicit,
keeps the model inside the modelled schemas, and bounds the result size. A rejected
statement is returned to the model as a tool error so it can correct itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FORBIDDEN_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "merge",
    "upsert",
    "replace into",
    "drop",
    "alter",
    "create",
    "truncate",
    "rename",
    "grant",
    "revoke",
    "attach",
    "detach",
    "copy",
    "export",
    "import",
    "install",
    "load",
    "pragma",
    "call",
    "set",
    "reset",
    "vacuum",
    "checkpoint",
    "begin",
    "commit",
    "rollback",
    "execute",
    "prepare",
    "declare",
    "script",
)
FORBIDDEN_FUNCTIONS = (
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "read_json",
    "read_json_auto",
    "read_text",
    "read_blob",
    "glob",
    "sniff_csv",
    "duckdb_",
    "sqlite_",
    "pg_",
    "current_setting",
    "external_query",
    "ml.",
    "session_user",
)
LEADING_KEYWORDS = ("select", "with")


class SQLGuardError(ValueError):
    """Raised when a statement violates the read-only / schema policy."""


@dataclass(frozen=True)
class GuardedSQL:
    original: str
    executable: str  # wrapped with a LIMIT so the warehouse never returns unbounded rows
    referenced_tables: tuple[str, ...]


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql.strip()


def _strip_string_literals(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def _cte_names(sql_no_literals: str) -> set[str]:
    return {
        m.group(1).lower()
        for m in re.finditer(r"(?:\bwith\s+|,\s*)([a-zA-Z_][\w]*)\s+as\s*\(", sql_no_literals, flags=re.I)
    }


def referenced_tables(sql: str) -> list[str]:
    """Identifiers that follow FROM / JOIN (CTE names excluded), lower-cased, backticks/quotes removed."""
    body = _strip_string_literals(strip_comments(sql))
    ctes = _cte_names(body)
    found: list[str] = []
    for m in re.finditer(
        r"\b(?:from|join)\s+([`\"]?[a-zA-Z_][\w\-]*(?:[`\"]?\.[`\"]?[a-zA-Z_][\w\-]*){0,2}[`\"]?)",
        body,
        flags=re.I,
    ):
        ident = m.group(1).replace("`", "").replace('"', "").lower()
        if ident in ctes or ident in found:
            continue
        found.append(ident)
    return found


def validate(sql: str, allowed_tables: set[str], max_rows: int, dialect: str = "duckdb") -> GuardedSQL:
    """Validate ``sql`` and return an executable, row-bounded version.

    ``allowed_tables`` holds fully qualified names ("analytics.fct_orders"); unqualified
    references resolve to the analytics schema. Anything else is rejected.
    """
    if not sql or not sql.strip():
        raise SQLGuardError("empty statement")
    body = strip_comments(sql).rstrip().rstrip(";").strip()
    if ";" in body:
        raise SQLGuardError("only a single statement is allowed")
    lowered = _strip_string_literals(body).lower()
    if not lowered.startswith(LEADING_KEYWORDS):
        raise SQLGuardError("only SELECT / WITH statements are allowed")
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"(?<![\w.]){re.escape(kw)}(?![\w])", lowered):
            raise SQLGuardError(f"forbidden keyword: {kw}")
    for fn in FORBIDDEN_FUNCTIONS:
        if fn in lowered:
            raise SQLGuardError(f"forbidden function or namespace: {fn}")
    if re.search(r"\b(?:from|join)\s+'", lowered):
        raise SQLGuardError("reading from file paths is not allowed")

    tables = referenced_tables(body)
    if not tables:
        raise SQLGuardError("the query must read from at least one warehouse table")
    allowed_lower = {t.lower() for t in allowed_tables}
    short_to_full = {t.split(".")[-1]: t for t in allowed_lower}
    resolved = []
    for t in tables:
        parts = t.split(".")
        candidate = t if len(parts) > 1 else short_to_full.get(t)
        if len(parts) == 3:  # project.dataset.table (BigQuery) -> dataset.table
            candidate = ".".join(parts[1:])
        if candidate is None or candidate not in allowed_lower:
            raise SQLGuardError(f"table '{t}' is not in the allowed warehouse schemas; use list_tables")
        resolved.append(candidate)

    fetch = max_rows + 1  # one extra row so callers can flag truncation
    executable = f"select * from (\n{body}\n) as _guarded limit {fetch}"
    return GuardedSQL(original=body, executable=executable, referenced_tables=tuple(resolved))


def normalise(sql: str) -> str:
    """Whitespace/case-insensitive form used to match the model's quoted SQL to executed SQL."""
    return re.sub(r"\s+", " ", strip_comments(sql).rstrip().rstrip(";")).strip().lower()
