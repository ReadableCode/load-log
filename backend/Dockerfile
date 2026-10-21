FROM python:3.13-slim

WORKDIR /app

# git: uv fetches the postgrest-auth dependency from its git tag
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# The build context is the REPO ROOT, not backend/, because the schema files the
# app applies at startup live in deploy/ at the top level (beside the dev stack's
# initdb mount). Everything below is therefore
# prefixed with backend/.
COPY backend/pyproject.toml backend/uv.lock ./

RUN uv sync --frozen --no-dev

COPY backend/src/ ./src/
COPY backend/scripts/ ./scripts/

# Streamlit reads .streamlit/config.toml from the working directory; without
# this the deployed app falls back to the default light theme (white
# dataframes, red buttons) even though the app CSS paints a dark page.
COPY backend/.streamlit/ ./.streamlit/

# Schema files applied by src/bootstrap.py at app startup. Copied flat to
# /app/deploy — bootstrap finds them by searching upward for deploy/02_schema.sql
# rather than by a fixed relative path, so this layout and the repo layout both
# resolve.
COPY deploy/02_schema.sql deploy/03_secure_users.sql ./deploy/

COPY backend/docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

ENV PYTHONPATH=/app/src

EXPOSE 8505

ENTRYPOINT ["./docker-entrypoint.sh"]

# Default to the Streamlit web app (the FastAPI surface was removed with the old
# direct-Postgres data layer). The compose services may still override this.
CMD ["uv", "run", "streamlit", "run", "src/web/app.py", \
     "--server.port=8505", "--server.address=0.0.0.0", "--server.headless=true"]
