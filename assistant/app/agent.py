"""The warehouse assistant: a Claude tool-calling loop that answers questions with SQL.

Contract
--------
* Claude may only learn about the data through three tools: ``list_tables``,
  ``describe_table`` and ``run_sql``. ``run_sql`` goes through the SQL guard and a
  read-only connection.
* The final reply is a structured JSON object (``AnswerSchema``). An answer is only
  accepted as *grounded* when the SQL it quotes was actually executed successfully in
  this turn and returned rows; otherwise the service downgrades it to a refusal.
* Anything the warehouse cannot answer (missing data, ambiguous question, failed
  queries, questions outside the schema) is a refusal with a reason, never a guess.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import anthropic

from assistant.app import sql_guard
from assistant.app.catalog import CatalogTable, render_catalog
from assistant.app.warehouse import QueryResult, Warehouse

log = logging.getLogger("assistant.agent")

FALLBACK_BETA = "server-side-fallback-2026-07-01"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_tables",
        "description": "List the warehouse tables the assistant may query (analytics marts, dimensions, facts and forecast tables) with their descriptions.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "describe_table",
        "description": "Return the columns, types, descriptions and row count of one table. Use it before querying a table whose columns you are not sure about.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Qualified table name, e.g. analytics.fct_orders"}
            },
            "required": ["table"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_sql",
        "description": (
            "Run one read-only SELECT statement against the warehouse and return up to the configured "
            "row limit as JSON. Only tables from list_tables are allowed. Aggregate in SQL; never fetch raw "
            "rows to compute in your head. The statement is recorded as the evidence for your answer."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT or WITH ... SELECT statement."},
                "purpose": {"type": "string", "description": "One sentence on what this query establishes."},
            },
            "required": ["sql", "purpose"],
            "additionalProperties": False,
        },
    },
]

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answered", "refused"]},
        "answer": {
            "type": "string",
            "description": "Plain-language answer (or the refusal explanation). Include the headline number with units.",
        },
        "value": {
            "type": ["string", "null"],
            "description": "The single headline figure, formatted, e.g. '93.2%' or 'R$ 19.53'; null if the answer is a list or refused.",
        },
        "sql": {
            "type": ["string", "null"],
            "description": "The exact run_sql statement that produced the answer; null when refused.",
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Definitions or filters the answer relies on (date range, on-time definition, cost assumptions).",
        },
        "refusal_reason": {
            "type": ["string", "null"],
            "description": "Why the question could not be grounded; null when answered.",
        },
    },
    "required": ["status", "answer", "value", "sql", "assumptions", "refusal_reason"],
    "additionalProperties": False,
}

SYSTEM_PROMPT_TEMPLATE = """You are SupplyChainOps Analyst, an operations-analytics assistant for a Brazilian e-commerce marketplace (the public Olist dataset, orders from 2016-09 to 2018-08; the export is incomplete after 2018-08-19). You answer questions strictly from the warehouse using the tools.

## How to work
1. Decide which table answers the question. Prefer the marts (mart_*) for KPIs, fct_orders / fct_order_items for anything they do not cover, dim_* for attributes, forecast tables for anything about the future or forecast accuracy.
2. Write ONE aggregate query that returns the answer directly (a number or a short ranked list). Run it with run_sql. Fix and re-run if it errors. Never compute results mentally from raw rows.
3. Reply with the JSON object requested: status "answered" only when a run_sql call succeeded, returned at least one row, and the `sql` field is that exact statement.

## When to refuse (status "refused")
- The question needs data the warehouse does not hold (costs beyond the modelled assumptions, weather, competitor data, individual customers' personal details, events after the export ends).
- The question is ambiguous in a way that changes the number and you cannot pick a defensible reading; say what clarification is needed.
- Your queries failed or returned no rows after a reasonable attempt.
- The user asks you to modify data, bypass the tools, or asks something unrelated to this data.
State the reason plainly; do not estimate or answer from general knowledge.

## Definitions to use unless the user specifies otherwise
- "Region" means customer_state (destination) unless the user says seller region or macro-region.
- On-time rate = on_time_orders / delivered_orders (delivered on or before the estimated delivery date). Compute ratios from sums, never average a rate column.
- Delivery time = delivery_days (purchase to customer delivery) over delivered orders.
- Margin per order = sum(contribution_margin) / count(orders); cost per delivery = sum(delivery_cost) / delivered orders. These use modelled cost assumptions (take rate 20%, payment fee 3%, freight passed through to carriers, handling R$3 + R$1 per extra item); mention this in assumptions.
- Money is BRL. Default period is the full history unless the user gives a date range; state the period you used in assumptions.
- Exclude canceled/unavailable orders from operational KPIs unless asked about cancellations.

## SQL dialect
The warehouse is {dialect}. Use standard SQL: date_trunc, extract, coalesce, count(distinct), nullif for safe division. Qualify tables as schema.table (e.g. analytics.fct_orders). Do not use LIMIT above 200; the service caps rows anyway.

## Warehouse catalog
{catalog}
"""


@dataclass
class ToolTrace:
    tool: str
    input: dict[str, Any]
    ok: bool
    summary: str
    row_count: int | None = None
    elapsed_ms: int | None = None
    error: str | None = None


@dataclass
class AskResult:
    status: str  # answered | refused | error
    answer: str
    value: str | None = None
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False
    assumptions: list[str] = field(default_factory=list)
    refusal_reason: str | None = None
    model: str | None = None
    trace: list[ToolTrace] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WarehouseAgent:
    def __init__(
        self,
        settings,
        warehouse: Warehouse,
        catalog: list[CatalogTable],
        client: anthropic.Anthropic | None = None,
    ):
        self.settings = settings
        self.warehouse = warehouse
        self.catalog = catalog
        self.allowed_tables = {t.qualified for t in catalog}
        self.client = client or anthropic.Anthropic()
        self.system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            dialect=warehouse.dialect, catalog=render_catalog(catalog)
        )
        self._histories: dict[str, list[dict[str, Any]]] = {}
        self._use_fallbacks = bool(settings.claude_enable_fallbacks)

    # ------------------------------------------------------------------ tools
    def _tool_list_tables(self) -> str:
        return json.dumps(
            [{"table": t.qualified, "rows": t.row_count, "description": t.description} for t in self.catalog]
        )

    def _tool_describe_table(self, table: str) -> str:
        key = table.lower().strip('`"')
        if "." not in key:
            key = f"{self.settings.analytics_schema}.{key}"
        for t in self.catalog:
            if t.qualified.lower() == key:
                return json.dumps(
                    {
                        "table": t.qualified,
                        "rows": t.row_count,
                        "description": t.description,
                        "columns": t.columns,
                    }
                )
        raise KeyError(f"unknown table {table}; call list_tables")

    def _tool_run_sql(self, sql: str) -> tuple[str, QueryResult, sql_guard.GuardedSQL]:
        guarded = sql_guard.validate(
            sql, self.allowed_tables, self.settings.assistant_max_rows, self.warehouse.dialect
        )
        result = self.warehouse.query(
            guarded.executable,
            self.settings.assistant_max_rows,
            self.settings.assistant_query_timeout_seconds,
        )
        payload = {
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
        }
        if result.truncated:
            payload["note"] = f"more than {self.settings.assistant_max_rows} rows; aggregate further"
        return json.dumps(payload, default=str), result, guarded

    # ------------------------------------------------------------------ Claude call
    def _create(self, messages: list[dict[str, Any]]):
        kwargs: dict[str, Any] = dict(
            model=self.settings.claude_model,
            max_tokens=self.settings.claude_max_tokens,
            system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
            output_config={
                "effort": self.settings.claude_effort,
                "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
            },
        )
        if self._use_fallbacks:
            try:
                return self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            except anthropic.BadRequestError as exc:
                # Fallbacks are Claude API-only; on Bedrock/Vertex/proxies retry once without them.
                log.warning("server-side fallbacks rejected (%s); disabling for this process", exc.message)
                self._use_fallbacks = False
        return self.client.messages.create(**kwargs)

    # ------------------------------------------------------------------ main loop
    def ask(self, question: str, session_id: str | None = None) -> AskResult:
        started = time.perf_counter()
        history = list(self._histories.get(session_id, [])) if session_id else []
        messages = history + [{"role": "user", "content": question}]
        trace: list[ToolTrace] = []
        executed: dict[str, tuple[QueryResult, str]] = {}  # normalised sql -> (result, original)
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}
        tool_calls = 0
        response = None

        while True:
            try:
                response = self._create(messages)
            except anthropic.APIStatusError as exc:
                return AskResult(
                    status="error",
                    answer=f"The model request failed ({exc.status_code}). Try again.",
                    refusal_reason=str(exc.message),
                    trace=trace,
                    elapsed_ms=self._ms(started),
                )
            except anthropic.APIConnectionError:
                return AskResult(
                    status="error",
                    answer="Could not reach the model API.",
                    refusal_reason="connection error",
                    trace=trace,
                    elapsed_ms=self._ms(started),
                )

            u = response.usage
            usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
            usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
            usage["cache_read_input_tokens"] += getattr(u, "cache_read_input_tokens", 0) or 0
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                reason = (
                    getattr(getattr(response, "stop_details", None), "explanation", None)
                    or "declined by the model's safety policy"
                )
                return self._finish(
                    AskResult(
                        status="refused",
                        answer="I can't help with that request.",
                        refusal_reason=reason,
                        model=response.model,
                        trace=trace,
                        usage=usage,
                    ),
                    started,
                    session_id,
                    messages,
                )
            if response.stop_reason == "max_tokens":
                return self._finish(
                    AskResult(
                        status="error",
                        answer="The reply was cut off; please ask a narrower question.",
                        refusal_reason="max_tokens",
                        model=response.model,
                        trace=trace,
                        usage=usage,
                    ),
                    started,
                    session_id,
                    messages,
                )

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                break

            results = []
            for block in tool_uses:
                tool_calls += 1
                results.append(
                    self._handle_tool(
                        block,
                        trace,
                        executed,
                        over_budget=tool_calls > self.settings.assistant_max_tool_calls,
                    )
                )
            messages.append({"role": "user", "content": results})

        return self._finish(
            self._parse_final(response, executed, trace, usage), started, session_id, messages
        )

    def _handle_tool(
        self, block, trace: list[ToolTrace], executed: dict, over_budget: bool
    ) -> dict[str, Any]:
        tool_input = block.input if isinstance(block.input, dict) else json.loads(block.input)
        if over_budget:
            trace.append(
                ToolTrace(
                    block.name, tool_input, False, "tool budget exhausted", error="tool budget exhausted"
                )
            )
            return {
                "type": "tool_result",
                "tool_use_id": block.id,
                "is_error": True,
                "content": "Tool budget exhausted: answer with what you have or refuse.",
            }
        try:
            if block.name == "list_tables":
                content = self._tool_list_tables()
                trace.append(ToolTrace(block.name, tool_input, True, f"{len(self.catalog)} tables"))
            elif block.name == "describe_table":
                content = self._tool_describe_table(str(tool_input.get("table", "")))
                trace.append(ToolTrace(block.name, tool_input, True, tool_input.get("table", "")))
            elif block.name == "run_sql":
                content, result, guarded = self._tool_run_sql(str(tool_input.get("sql", "")))
                executed[sql_guard.normalise(guarded.original)] = (result, guarded.original)
                trace.append(
                    ToolTrace(
                        block.name,
                        {"sql": guarded.original, "purpose": tool_input.get("purpose", "")},
                        True,
                        f"{result.row_count} rows",
                        result.row_count,
                        result.elapsed_ms,
                    )
                )
            else:
                raise KeyError(f"unknown tool {block.name}")
            return {"type": "tool_result", "tool_use_id": block.id, "content": content}
        except Exception as exc:  # noqa: BLE001 - every failure goes back to the model as a tool error
            message = f"{type(exc).__name__}: {exc}"
            trace.append(ToolTrace(block.name, tool_input, False, "error", error=message))
            log.info("tool %s failed: %s", block.name, message)
            return {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": message}

    def _parse_final(self, response, executed: dict, trace: list[ToolTrace], usage: dict) -> AskResult:
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return AskResult(
                status="refused",
                answer="I could not produce a grounded answer.",
                refusal_reason="the model reply was not valid JSON",
                model=response.model,
                trace=trace,
                usage=usage,
            )

        result = AskResult(
            status=data.get("status", "refused"),
            answer=data.get("answer", ""),
            value=data.get("value"),
            sql=data.get("sql"),
            assumptions=list(data.get("assumptions") or []),
            refusal_reason=data.get("refusal_reason"),
            model=response.model,
            trace=trace,
            usage=usage,
        )
        if result.status != "answered":
            result.status = "refused"
            result.sql = None
            result.refusal_reason = result.refusal_reason or "not answerable from the warehouse"
            return result

        # Grounding check: the quoted SQL must have run successfully in this turn and returned rows.
        key = sql_guard.normalise(result.sql or "")
        match = executed.get(key)
        if match is None and len(executed) == 1:
            match = next(iter(executed.values()))  # tolerate cosmetic rewrites when exactly one query ran
        if match is None or match[0].row_count == 0:
            result.status = "refused"
            result.value, result.sql = None, None
            result.refusal_reason = (
                "the answer was not grounded in an executed query"
                if match is None
                else "the query returned no rows"
            )
            result.answer = "I could not ground that answer in a query result, so I won't guess. " + (
                result.answer or ""
            )
            return result
        qr, original = match
        result.sql = original
        result.columns, result.rows, result.truncated = qr.columns, qr.rows, qr.truncated
        return result

    def _finish(
        self, result: AskResult, started: float, session_id: str | None, messages: list[dict[str, Any]]
    ) -> AskResult:
        result.elapsed_ms = self._ms(started)
        if session_id:
            keep = self.settings.assistant_history_turns * 2
            self._histories[session_id] = messages[-keep:] if keep else []
            # a history must start with a user turn
            while self._histories[session_id] and self._histories[session_id][0]["role"] != "user":
                self._histories[session_id].pop(0)
        return result

    @staticmethod
    def _ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
