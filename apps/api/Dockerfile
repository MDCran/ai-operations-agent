FROM ghcr.io/astral-sh/uv:0.10.9 AS uv
FROM python:3.12-slim AS runtime
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
RUN useradd --create-home operations && mkdir -p uploads && chown operations:operations /app /app/uploads
COPY --chown=operations:operations . .
USER operations
EXPOSE 8000

FROM runtime AS test
USER root
RUN uv sync --frozen
USER operations
