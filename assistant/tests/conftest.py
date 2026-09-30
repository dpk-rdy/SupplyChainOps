import json
from types import SimpleNamespace

import duckdb
import pytest

from assistant.app.agent import WarehouseAgent
from assistant.app.catalog import build_catalog
from assistant.app.config import Settings
from assistant.app.warehouse import DuckDBWarehouse


@pytest.fixture
def warehouse_path(tmp_path):
    path = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(path))
    con.execute("create schema analytics")
    con.execute("""
        create table analytics.fct_orders as
        select * from (values
            ('o1', 'SP', true, true, 8.0, 20.0),
            ('o2', 'SP', true, false, 15.0, 18.0),
            ('o3', 'RJ', true, true, 10.0, 22.0),
            ('o4', 'RJ', false, null, null, 5.0)
        ) t(order_id, customer_state, is_delivered, is_on_time, delivery_days, contribution_margin)
    """)
    con.execute("create table analytics.dim_regions as select 'SP' state_code, 'Sudeste' macro_region")
    con.close()
    return str(path)


@pytest.fixture
def settings(warehouse_path):
    return Settings(
        warehouse_backend="duckdb",
        duckdb_path=warehouse_path,
        anthropic_api_key="test",
        dbt_manifest_path="/nonexistent/manifest.json",
        claude_enable_fallbacks=False,
    )


# ---------------------------------------------------------------- fake Claude client
def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(name, input, id="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=input, id=id)


def final_json(**fields):
    base = {
        "status": "answered",
        "answer": "",
        "value": None,
        "sql": None,
        "assumptions": [],
        "refusal_reason": None,
    }
    base.update(fields)
    return text_block(json.dumps(base))


def response(content, stop_reason="end_turn"):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        stop_details=None,
        model="claude-test",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0),
    )


class FakeMessages:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        if not self.scripted:
            raise AssertionError("fake client ran out of scripted responses")
        return self.scripted.pop(0)


class FakeClient:
    def __init__(self, scripted):
        self.messages = FakeMessages(scripted)
        self.beta = SimpleNamespace(messages=self.messages)


@pytest.fixture
def make_agent(settings):
    def _make(scripted, **overrides):
        s = settings.model_copy(update=overrides) if overrides else settings
        wh = DuckDBWarehouse(s.duckdb_path, ("analytics", "forecasts"))
        catalog = build_catalog(wh, s.dbt_manifest_path)
        return WarehouseAgent(s, wh, catalog, client=FakeClient(scripted))

    return _make
