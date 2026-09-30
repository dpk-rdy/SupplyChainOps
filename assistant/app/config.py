"""Runtime settings for the assistant (12-factor: everything comes from the environment)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Warehouse
    warehouse_backend: str = Field(default="duckdb", pattern="^(duckdb|bigquery)$")
    duckdb_path: str = "data/warehouse/supplychainops.duckdb"
    gcp_project: str | None = None
    bq_location: str = "US"
    bq_dataset_analytics: str = "analytics"
    forecast_schema: str = "forecasts"
    analytics_schema: str = "analytics"
    bq_maximum_bytes_billed: int = 2_000_000_000  # 2 GB per query
    dbt_manifest_path: str = "dbt/target/manifest.json"

    # Claude
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = Field(default="medium", pattern="^(low|medium|high|xhigh|max)$")
    claude_max_tokens: int = 8000
    claude_enable_fallbacks: bool = True

    # Guardrails
    assistant_max_rows: int = 200
    assistant_max_tool_calls: int = 8
    assistant_query_timeout_seconds: int = 30
    assistant_history_turns: int = 6

    # Slack
    slack_bot_token: str | None = None
    slack_app_token: str | None = None
    assistant_api_url: str = "http://localhost:8000"


def get_settings() -> Settings:
    return Settings()
