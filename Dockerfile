# ─── Multi-stage Docker Build ────────────────────────────────────
# Stage 1: Builder
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -e .[dev]

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    TZ=UTC

RUN groupadd -r cryptoai && \
    useradd -r -g cryptoai -d /app -s /sbin/nologin cryptoai && \
    mkdir -p /app/{configs,logs,data} && \
    chown -R cryptoai:cryptoai /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

COPY --chown=cryptoai:cryptoai . /app
WORKDIR /app

USER cryptoai

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
