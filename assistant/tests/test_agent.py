import json

from assistant.tests.conftest import final_json, response, text_block, tool_block

SQL = "select customer_state, sum(case when is_on_time then 1 else 0 end) * 1.0 / sum(case when is_delivered then 1 else 0 end) as on_time_rate from analytics.fct_orders group by 1 order by 1"


def test_grounded_answer_returns_sql_and_rows(make_agent):
    agent = make_agent(
        [
            response(
                [tool_block("run_sql", {"sql": SQL, "purpose": "on-time by state"})], stop_reason="tool_use"
            ),
            response(
                [
                    final_json(
                        answer="On-time rate is 50% in SP and 100% in RJ.",
                        value="50% / 100%",
                        sql=SQL,
                        assumptions=["full history"],
                    )
                ]
            ),
        ]
    )
    result = agent.ask("What is the on-time rate by state?")
    assert result.status == "answered"
    assert result.sql == SQL
    assert result.columns == ["customer_state", "on_time_rate"]
    assert result.rows == [["RJ", 1.0], ["SP", 0.5]]
    assert result.trace[0].tool == "run_sql" and result.trace[0].ok
    # the tool result went back to the model as JSON rows
    second_call = agent.client.messages.calls[1]
    tool_result = second_call["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and '"row_count": 2' in tool_result["content"]
    assert second_call["output_config"]["format"]["type"] == "json_schema"


def test_answer_without_executed_query_is_downgraded_to_refusal(make_agent):
    agent = make_agent(
        [response([final_json(answer="About 93%.", value="93%", sql="select 1 from analytics.fct_orders")])]
    )
    result = agent.ask("What is the on-time rate?")
    assert result.status == "refused"
    assert result.sql is None and result.value is None
    assert "not grounded" in result.refusal_reason


def test_empty_result_is_refused(make_agent):
    sql = "select * from analytics.fct_orders where customer_state = 'ZZ'"
    agent = make_agent(
        [
            response([tool_block("run_sql", {"sql": sql, "purpose": "zz"})], stop_reason="tool_use"),
            response([final_json(answer="ZZ had orders.", value="1", sql=sql)]),
        ]
    )
    result = agent.ask("Orders in ZZ?")
    assert result.status == "refused" and "no rows" in result.refusal_reason


def test_model_refusal_is_passed_through(make_agent):
    agent = make_agent(
        [
            response(
                [
                    final_json(
                        status="refused",
                        answer="The warehouse has no weather data.",
                        refusal_reason="no weather data",
                    )
                ]
            )
        ]
    )
    result = agent.ask("Did rain delay deliveries?")
    assert result.status == "refused" and result.refusal_reason == "no weather data" and result.sql is None


def test_guard_rejection_is_returned_as_tool_error(make_agent):
    agent = make_agent(
        [
            response(
                [tool_block("run_sql", {"sql": "delete from analytics.fct_orders", "purpose": "oops"})],
                stop_reason="tool_use",
            ),
            response(
                [
                    final_json(
                        status="refused", answer="I can only read data.", refusal_reason="write requested"
                    )
                ]
            ),
        ]
    )
    result = agent.ask("Delete all orders")
    assert result.status == "refused"
    assert result.trace[0].ok is False and "SQLGuardError" in result.trace[0].error
    tool_result = agent.client.messages.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True


def test_list_and_describe_tools(make_agent):
    agent = make_agent(
        [
            response(
                [
                    tool_block("list_tables", {}, id="a"),
                    tool_block("describe_table", {"table": "fct_orders"}, id="b"),
                ],
                stop_reason="tool_use",
            ),
            response(
                [final_json(status="refused", answer="Need clarification.", refusal_reason="ambiguous")]
            ),
        ]
    )
    agent.ask("What tables exist?")
    results = agent.client.messages.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]
    described = json.loads(results[1]["content"])
    assert described["table"] == "analytics.fct_orders" and {c["name"] for c in described["columns"]} >= {
        "order_id",
        "customer_state",
    }


def test_tool_budget_is_enforced(make_agent):
    sql = "select count(*) from analytics.fct_orders"
    calls = [
        response([tool_block("run_sql", {"sql": sql, "purpose": "n"}, id=f"t{i}")], stop_reason="tool_use")
        for i in range(3)
    ]
    calls.append(response([final_json(status="refused", answer="budget", refusal_reason="budget")]))
    agent = make_agent(calls, assistant_max_tool_calls=2)
    result = agent.ask("count")
    assert result.status == "refused"
    assert result.trace[-1].error == "tool budget exhausted"


def test_session_history_is_kept_between_questions(make_agent):
    sql = "select count(*) as n from analytics.fct_orders"
    agent = make_agent(
        [
            response([tool_block("run_sql", {"sql": sql, "purpose": "n"})], stop_reason="tool_use"),
            response([final_json(answer="4 orders", value="4", sql=sql)]),
            response([final_json(status="refused", answer="", refusal_reason="x")]),
        ]
    )
    agent.ask("How many orders?", session_id="s1")
    agent.ask("And in SP?", session_id="s1")
    third_call = agent.client.messages.calls[2]
    assert (
        third_call["messages"][0]["role"] == "user"
        and third_call["messages"][0]["content"] == "How many orders?"
    )
    assert third_call["messages"][-1]["content"] == "And in SP?"


def test_invalid_json_reply_is_refused(make_agent):
    agent = make_agent([response([text_block("not json")])])
    result = agent.ask("anything")
    assert result.status == "refused" and "valid JSON" in result.refusal_reason
