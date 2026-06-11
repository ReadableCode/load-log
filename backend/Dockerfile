FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

COPY src/ ./src/

ENV PYTHONPATH=/app/src

EXPOSE 8000 8505

CMD ["uv", "run", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
