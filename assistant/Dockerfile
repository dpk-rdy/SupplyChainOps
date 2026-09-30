# Assistant image: runs the FastAPI service (default) or the Slack bot (override CMD).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY assistant/requirements.txt /app/assistant/requirements.txt
RUN pip install --no-cache-dir -r /app/assistant/requirements.txt

COPY assistant /app/assistant
# dbt manifest gives the assistant table/column descriptions (run `make dbt-docs` before building)
COPY dbt/target/manifest.json /app/dbt/target/manifest.json

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "assistant.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
