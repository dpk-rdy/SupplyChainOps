"""FastAPI surface for the warehouse assistant.

uvicorn assistant.app.main:app --reload
curl -s localhost:8000/ask -H 'content-type: application/json' -d '{"question": "What was the on-time delivery rate in SP in 2018?"}'
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import anyio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from assistant.app.agent import WarehouseAgent
from assistant.app.catalog import build_catalog
from assistant.app.config import Settings, get_settings
from assistant.app.warehouse import connect

log = logging.getLogger("assistant.api")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    session_id: str | None = Field(
        default=None, max_length=200, description="Conversation key for follow-up questions"
    )


class AskResponse(BaseModel):
    status: str
    answer: str
    value: str | None
    sql: str | None
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    assumptions: list[str]
    refusal_reason: str | None
    model: str | None
    trace: list[dict[str, Any]]
    usage: dict[str, int]
    elapsed_ms: int


def build_agent(settings: Settings, client=None) -> WarehouseAgent:
    warehouse = connect(settings)
    catalog = build_catalog(warehouse, settings.dbt_manifest_path)
    if not catalog:
        raise RuntimeError("no warehouse tables found; run `make load dbt-build` first")
    return WarehouseAgent(settings, warehouse, catalog, client=client)


def create_app(settings: Settings | None = None, agent: WarehouseAgent | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.agent = agent or build_agent(settings)
        log.info(
            "assistant ready: backend=%s model=%s tables=%d",
            settings.warehouse_backend,
            settings.claude_model,
            len(app.state.agent.catalog),
        )
        yield

    app = FastAPI(title="SupplyChainOps Assistant", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "backend": settings.warehouse_backend, "model": settings.claude_model}

    @app.get("/tables")
    def tables() -> list[dict[str, Any]]:
        return [
            {"table": t.qualified, "rows": t.row_count, "description": t.description}
            for t in app.state.agent.catalog
        ]

    @app.get("/tables/{name}")
    def table(name: str) -> dict[str, Any]:
        key = name if "." in name else f"{settings.analytics_schema}.{name}"
        for t in app.state.agent.catalog:
            if t.qualified == key:
                return {
                    "table": t.qualified,
                    "rows": t.row_count,
                    "description": t.description,
                    "columns": t.columns,
                }
        raise HTTPException(404, f"unknown table {name}")

    @app.post("/ask", response_model=AskResponse)
    async def ask(req: AskRequest) -> AskResponse:
        # The agent loop is synchronous (SDK + warehouse); run it off the event loop.
        result = await anyio.to_thread.run_sync(app.state.agent.ask, req.question, req.session_id)
        return AskResponse(**result.to_dict())

    return app


app = create_app()
