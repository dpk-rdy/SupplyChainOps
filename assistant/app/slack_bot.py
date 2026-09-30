"""Slack front-end for the assistant (Socket Mode, so no public URL is needed).

Mention the bot in a channel or DM it. Each thread is a conversation (session_id), so
follow-ups like "and for RJ?" work. Replies carry the answer and the SQL that produced it.

Slack app manifest essentials: Socket Mode on; bot token scopes app_mentions:read,
chat:write, im:history, im:read, im:write; event subscriptions app_mention and
message.im. Tokens: SLACK_BOT_TOKEN (xoxb-) and SLACK_APP_TOKEN (xapp-).
"""

from __future__ import annotations

import logging
import os
import re

import httpx
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

log = logging.getLogger("assistant.slack")

API_URL = os.environ.get("ASSISTANT_API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = float(os.environ.get("ASSISTANT_SLACK_TIMEOUT", "180"))


def format_reply(result: dict) -> str:
    status = result.get("status")
    if status == "answered":
        head = f"*{result['value']}*  {result['answer']}" if result.get("value") else result["answer"]
        parts = [head]
        if result.get("assumptions"):
            parts.append("_Assumptions: " + "; ".join(result["assumptions"]) + "_")
        if result.get("sql"):
            parts.append(f"```{result['sql'].strip()}```")
        if result.get("truncated"):
            parts.append("_Result truncated to the first rows._")
        return "\n".join(parts)
    if status == "refused":
        return f":no_entry_sign: I can't answer that from the warehouse. {result.get('answer', '')}\n_Reason: {result.get('refusal_reason')}_"
    return f":warning: Something went wrong: {result.get('answer', '')}"


def ask_api(question: str, session_id: str) -> dict:
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(f"{API_URL}/ask", json={"question": question, "session_id": session_id})
        resp.raise_for_status()
        return resp.json()


def strip_mention(text: str) -> str:
    return re.sub(r"<@[A-Z0-9]+>", "", text or "").strip()


def build_app() -> App:
    app = App(token=os.environ["SLACK_BOT_TOKEN"])

    def handle(event, say):
        question = strip_mention(event.get("text", ""))
        if not question:
            say(
                "Ask me a question about orders, deliveries, margins or forecasts.",
                thread_ts=event.get("thread_ts") or event.get("ts"),
            )
            return
        thread_ts = event.get("thread_ts") or event.get("ts")
        session_id = f"{event.get('channel')}:{thread_ts}"
        try:
            result = ask_api(question, session_id)
        except httpx.HTTPError as exc:
            log.exception("assistant API call failed")
            say(f":warning: The assistant API is unavailable ({exc}).", thread_ts=thread_ts)
            return
        say(format_reply(result), thread_ts=thread_ts)

    @app.event("app_mention")
    def on_mention(event, say):
        handle(event, say)

    @app.event("message")
    def on_message(event, say):
        if event.get("channel_type") == "im" and not event.get("bot_id") and event.get("subtype") is None:
            handle(event, say)

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    SocketModeHandler(build_app(), os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
