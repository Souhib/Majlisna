# Multi-stage build for IBG backend

# Stage 1: Base with Python and uv
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Stage 2: Install dependencies
FROM base AS dependencies

# Install build dependencies for C extensions
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and create minimal package structure for dependency resolution
COPY pyproject.toml ./
RUN mkdir -p ipg && touch ipg/__init__.py

# Install dependencies using uv (from pyproject.toml)
# INSTALL_DEV=true installs dev extras (faker, etc.) needed for E2E data seeding
ARG INSTALL_DEV=false
RUN uv venv && if [ "$INSTALL_DEV" = "true" ]; then uv pip install --no-cache ".[dev]"; else uv pip install --no-cache .; fi

# Stage 3: Production
FROM base AS production

# Copy installed venv from dependencies stage
COPY --from=dependencies /app/.venv /app/.venv

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--proxy-headers", "--forwarded-allow-ips", "*", "--loop", "uvloop", "--http", "httptools", "--workers", "4"]
