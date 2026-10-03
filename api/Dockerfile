# planet-hunter API image (Render free web service; see docs/DEPLOY.md).
#
# The build context is api/ alone:
#   docker build -t planet-hunter-api api
#   docker run --rm -p 8000:8000 -e PORT=8000 -e PH_DATABASE_URL=postgresql://... planet-hunter-api
# Without PH_DATABASE_URL it uses a throwaway SQLite file inside the container.
#
# The `finder` extra (pixels/ + pipeline/: astropy, lightkurve, ...) is NOT installed: the web API
# never imports it. Ingestion (python -m api.finder_ingest) runs on the Oracle server instead.
#
# Migrations: the app applies pending ones on startup (advisory lock). To apply them on their own:
#   docker run --rm -e PH_DATABASE_URL=... planet-hunter-api python -m api.migrate

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_NO_CACHE=1
WORKDIR /src
# Dependencies first (cached while only the code changes), then the project itself.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:${PYTHON_VERSION}-slim-bookworm
RUN useradd --create-home --uid 1000 app
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    PH_DB_PATH=/tmp/ph.db \
    PH_ADAPTERS=fake
USER app
WORKDIR /home/app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/healthz', timeout=4)" || exit 1
# Migrations first, on every start (Render's pre-deploy command is for paid plans only): idempotent, under an
# advisory lock, and a failure stops this deploy before it serves (Render keeps the previous one live).
# Shell form so Render's $PORT is used; exec keeps uvicorn as PID 1 (clean SIGTERM).
# The client IP comes from PH_TRUSTED_PROXY_HOPS (the app reads X-Forwarded-For itself).
CMD ["sh", "-c", "python -m api.migrate && exec uvicorn --factory api.app:create_app --host 0.0.0.0 --port \"$PORT\""]
