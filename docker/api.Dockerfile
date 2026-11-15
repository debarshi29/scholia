# Scholia API. Build from the repository root:  docker build -f docker/api.Dockerfile -t scholia-api .
FROM python:3.12-slim

# git: the corpus build clones repositories (GitPython needs the binary).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/data/hf

WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY schema ./schema
COPY corpus ./corpus
COPY api ./api
RUN uv sync --locked --no-dev

# Non-root, with the two writable locations the app needs.
RUN useradd --create-home --uid 1000 scholia \
    && mkdir -p /app/data /app/problems \
    && chown -R scholia:scholia /app/data /app/problems
USER scholia

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# Bound to all interfaces inside the container only; compose publishes it on 127.0.0.1.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
