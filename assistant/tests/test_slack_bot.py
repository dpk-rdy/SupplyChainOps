from assistant.app import slack_bot


def test_format_reply_answered_includes_value_sql_and_assumptions():
    text = slack_bot.format_reply(
        {
            "status": "answered",
            "answer": "On-time rate was 93.2%.",
            "value": "93.2%",
            "sql": "select 1 from analytics.fct_orders",
            "assumptions": ["full history"],
            "truncated": False,
        }
    )
    assert (
        text.startswith("*93.2%*")
        and "```select 1 from analytics.fct_orders```" in text
        and "full history" in text
    )


def test_format_reply_refused_gives_reason():
    text = slack_bot.format_reply(
        {"status": "refused", "answer": "No weather data.", "refusal_reason": "not in warehouse"}
    )
    assert "can't answer" in text and "not in warehouse" in text


def test_strip_mention():
    assert slack_bot.strip_mention("<@U123ABC> on-time rate in SP?") == "on-time rate in SP?"
