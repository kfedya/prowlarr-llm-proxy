# Stage 1: Build dependencies with poetry
FROM python:3.13-slim AS builder

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-root --no-interaction --no-ansi

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application
COPY app ./app
COPY entrypoint.sh ./

RUN chmod +x entrypoint.sh

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Default: single port mode
ENV PORT=8080
ENV UPSTREAM_URL=http://localhost:8989

# Multi-port mode: set ROUTES instead
# ENV ROUTES='{"8585": "http://sonarr:8989", "8586": "http://prowlarr:9696"}'

EXPOSE 8080 8585 8586

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:${PORT:-8080}/health', timeout=5).raise_for_status()"

CMD ["./entrypoint.sh"]
