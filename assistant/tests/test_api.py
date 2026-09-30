from fastapi.testclient import TestClient

from assistant.app.main import create_app
from assistant.tests.conftest import final_json, response, tool_block


def test_api_endpoints(make_agent, settings):
    sql = "select count(*) as n from analytics.fct_orders"
    agent = make_agent(
        [
            response([tool_block("run_sql", {"sql": sql, "purpose": "n"})], stop_reason="tool_use"),
            response([final_json(answer="There are 4 orders.", value="4", sql=sql)]),
        ]
    )
    app = create_app(settings, agent=agent)
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        tables = client.get("/tables").json()
        assert {t["table"] for t in tables} == {"analytics.fct_orders", "analytics.dim_regions"}
        assert client.get("/tables/fct_orders").json()["rows"] == 4
        assert client.get("/tables/nope").status_code == 404

        r = client.post("/ask", json={"question": "How many orders?"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "answered" and body["sql"] == sql and body["rows"] == [[4]]
        assert client.post("/ask", json={"question": "hi"}).status_code == 422
