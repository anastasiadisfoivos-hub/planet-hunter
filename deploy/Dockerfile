# planet-hunter API image.
#
# Build from the REPO ROOT (the context must contain api/, and pipeline/ sources/ forecast/ once
# they exist):
#   docker build -f deploy/Dockerfile -t planet-hunter-api .
#   docker run --rm -p 8000:8000 planet-hunter-api          # fakes on, docs at :8000/docs
#
# deploy/Dockerfile.dockerignore keeps web/, .git and local venvs out of the context.
#
# How the sibling packages get in:
#   - If api/pyproject.toml lists them as uv path dependencies, `uv sync` installs them from the
#     lock file.
#   - Otherwise every pipeline/ sources/ forecast/ folder with a pyproject.toml is installed into
#     the same venv. Set --build-arg WITH_SIBLINGS=0 to build api/ alone.
#
# Pre-warmed TESS cache (optional, needs network at build time):
#   docker build -f deploy/Dockerfile --build-arg PREWARM_STARS="WASP-18,WASP-121,WASP-43,TOI-700" .
# runs `python -m hunter <star>` for each star, so the downloaded light curves and star lookups
# are baked into the image. They survive Render's disk wipes because they're part of the image.
# Empty by default: CI builds stay offline and fast.

ARG PYTHON_VERSION=3.12

# ---------- build: resolve and install into /opt/venv ----------
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS build

ARG WITH_SIBLINGS=1
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src
COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    test -f api/pyproject.toml || { echo "api/ is missing from the build context" >&2; exit 1; } \
 && uv sync --project api --frozen --no-dev --no-editable \
 && if [ "$WITH_SIBLINGS" = "1" ]; then \
      for pkg in pipeline sources forecast; do \
        if [ -f "$pkg/pyproject.toml" ]; then \
          echo "installing sibling $pkg/"; \
          uv pip install --python /opt/venv/bin/python "./$pkg"; \
        fi; \
      done; \
    fi

# ---------- runtime ----------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# uid 1000 matches what Hugging Face Spaces runs containers as.
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /data \
 && chown app:app /data

COPY --from=build /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/app \
    MPLCONFIGDIR=/tmp/matplotlib \
    PORT=8000 \
    PH_DB_PATH=/data/traps.db \
    PH_ADAPTERS=fake \
    HUNTER_CACHE_DIR=/home/app/.cache/planet-hunter/pipeline

USER app
WORKDIR /home/app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/healthz', timeout=4)" || exit 1

# ---------- final: runtime, plus the pre-warmed cache when PREWARM_STARS is set ----------
FROM runtime
ARG PREWARM_STARS=""
# Change this (e.g. to the date) to refresh the cache instead of reusing the cached layer.
ARG PREWARM_STAMP=""
RUN if [ -z "$PREWARM_STARS" ]; then exit 0; fi; \
    if ! python -c "import hunter" 2>/dev/null; then echo "pipeline/ not installed: skipping prewarm"; exit 0; fi; \
    echo "$PREWARM_STARS" | tr ',' '\n' | while read -r star; do \
      [ -n "$star" ] || continue; \
      echo "prewarming $star"; \
      python -W ignore -m hunter "$star" --out /tmp/prewarm >/dev/null || echo "prewarm failed: $star (continuing)"; \
    done; \
    rm -rf /tmp/prewarm; \
    du -sh "$HUNTER_CACHE_DIR" 2>/dev/null || true

# Shell form so $PORT (set by Render / Koyeb / HF Spaces) is honoured. exec keeps uvicorn as PID 1.
CMD ["sh", "-c", "exec uvicorn --factory api.app:create_app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*'"]
