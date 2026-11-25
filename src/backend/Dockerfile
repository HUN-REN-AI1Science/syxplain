# syntax=docker/dockerfile:1
# Builder stage
FROM python:3.10-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

COPY requirements.txt /tmp/requirements.txt
# All dependencies ship wheels for python3.10/x86_64, so no compiler is needed.
# The cache mount keeps downloaded wheels between local builds.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /usr/local/bin/python --prefix=/install -r /tmp/requirements.txt

# Runtime stage
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Non-root user and the volume directories, owned by it
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/logs /app/data /app/outputs \
    && chown appuser:appuser /app /app/logs /app/data /app/outputs

COPY --from=builder /install /usr/local

# Only the backend package is needed at runtime (alembic + progress config live in it)
COPY --chown=appuser:appuser src/backend/ /app/backend/

USER appuser

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
