# Warehouse assistant

Ask questions about orders, deliveries, margins and forecasts; get the number and the SQL.

```bash
cp ../.env.example ../.env                 # set ANTHROPIC_API_KEY (and Slack tokens for the bot)
make api                                   # from the repo root
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "Which macro-region had the worst on-time rate in Q1 2018?", "session_id": "demo"}'
```

Response shape:

```json
{
  "status": "answered",            // answered | refused | error
  "answer": "Norte had the lowest on-time rate in Q1 2018 at 78.4% ...",
  "value": "78.4%",
  "sql": "select customer_macro_region, ... from analytics.fct_orders where ...",
  "columns": ["customer_macro_region", "on_time_rate"],
  "rows": [["Norte", 0.784], ...],
  "assumptions": ["Q1 2018 = purchase dates 2018-01-01..2018-03-31", "on-time = delivered on/before estimated date"],
  "refusal_reason": null,
  "trace": [{"tool": "run_sql", "input": {...}, "ok": true, "row_count": 5, "elapsed_ms": 12}],
  "usage": {"input_tokens": 5210, "output_tokens": 310, "cache_read_input_tokens": 4800}
}
```

A refusal looks like `{"status": "refused", "answer": "...", "refusal_reason": "the warehouse has no weather data"}`
and never carries SQL or a value.

## Endpoints

- `POST /ask` `{question, session_id?}` — session_id keeps follow-ups in context.
- `GET /tables`, `GET /tables/{name}` — the catalog Claude sees.
- `GET /health`.

## Slack

Create a Slack app (Socket Mode on; scopes `app_mentions:read`, `chat:write`, `im:history`, `im:read`,
`im:write`; events `app_mention`, `message.im`). Put `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in `.env`,
then `make slack` (or the `slack` service in docker compose). Each Slack thread is one session.

## Docker

```bash
make dbt-docs                                   # manifest.json gives the assistant column descriptions
docker compose -f assistant/docker-compose.yml up --build
```

The DuckDB warehouse is mounted read-only into the `api` container; for BigQuery set
`WAREHOUSE_BACKEND=bigquery`, `GCP_PROJECT` and mount a service-account key.

## Configuration

See `.env.example`. Notable: `CLAUDE_MODEL` (default `claude-opus-5-5`), `CLAUDE_EFFORT`,
`CLAUDE_ENABLE_FALLBACKS`, `ASSISTANT_MAX_ROWS`, `ASSISTANT_MAX_TOOL_CALLS`, `ASSISTANT_QUERY_TIMEOUT_SECONDS`.
