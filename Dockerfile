FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --locked --no-dev
COPY alembic.ini ./
COPY alembic ./alembic

ENV PATH="/app/.venv/bin:$PATH"

# data/ is mounted as a volume; apply migrations and seed before the API starts. One worker only:
# the scheduler runs inside the API process.
CMD ["sh", "-c", "alembic upgrade head && python -m ria_stats.seed && uvicorn ria_stats.api:app --host 0.0.0.0 --port 8000 --workers 1"]
