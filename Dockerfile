FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --locked --no-dev
COPY alembic.ini ./
COPY alembic ./alembic

ENV PATH="/app/.venv/bin:$PATH"

# data/ is mounted as a volume; apply migrations and seed before the scheduler starts.
CMD ["sh", "-c", "alembic upgrade head && python -m ria_stats.seed && python -m ria_stats.scheduler"]
