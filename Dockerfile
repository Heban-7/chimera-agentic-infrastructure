# =============================================================================
# Project Chimera — Multi-Stage Docker Build
# Base: python:3.12-slim | Package Manager: uv
# Ref: specs/technical.md §8 (Technology Stack)
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — Install uv and resolve dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies required for building native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv — fast Python package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files first (layer caching optimization)
COPY pyproject.toml uv.lock* ./

# Install dependencies using uv into a virtual environment
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install --no-cache \
    pydantic>=2.0 \
    pydantic-ai \
    weaviate-client>=4.0 \
    coinbase-agentkit \
    redis>=5.0 \
    asyncpg \
    httpx \
    python-dotenv \
    pytest \
    pytest-asyncio \
    pytest-cov

# ---------------------------------------------------------------------------
# Stage 2: Runtime — Slim production image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd --gid 1000 chimera && \
    useradd --uid 1000 --gid chimera --shell /bin/bash --create-home chimera

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY src/ ./src/
COPY specs/ ./specs/
COPY skills/ ./skills/
COPY tests/ ./tests/
COPY Makefile pyproject.toml ./

# Set ownership
RUN chown -R chimera:chimera /app

# Switch to non-root user
USER chimera

# Health check — verify Python and key packages are importable
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import pydantic; import redis; print('healthy')" || exit 1

# Default command: run the test suite
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
