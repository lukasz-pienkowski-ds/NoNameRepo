FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . .
RUN uv sync --locked

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# DuckDB downloads extensions on first load. Baking quack in keeps container
# start offline-safe and makes a failure show up at build time rather than when
# the team is trying to demo. Only quack: retrieval uses array_cosine_similarity,
# which is a core function, so vss is not needed.
RUN python -c "\
import duckdb; \
con = duckdb.connect(); \
con.execute('INSTALL quack'); \
con.execute('LOAD quack')"

EXPOSE 8888

CMD ["python", "db/init_db.py"]
