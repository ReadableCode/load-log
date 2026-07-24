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
COPY scripts/ ./scripts/

# Streamlit reads .streamlit/config.toml from the working directory; without
# this the deployed app falls back to the default light theme (white
# dataframes, red buttons) even though the app CSS paints a dark page.
COPY .streamlit/ ./.streamlit/

# Alembic config + migrations. The entrypoint runs `alembic upgrade head`
# before whatever CMD/compose-command is passed, so migrations apply first for
# every service that uses this image.
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

ENV PYTHONPATH=/app/src

EXPOSE 8505

ENTRYPOINT ["./docker-entrypoint.sh"]

# Default to the Streamlit web app (the FastAPI surface was removed with the old
# direct-Postgres data layer). The compose services may still override this.
CMD ["uv", "run", "streamlit", "run", "src/web/app.py", \
     "--server.port=8505", "--server.address=0.0.0.0", "--server.headless=true"]
