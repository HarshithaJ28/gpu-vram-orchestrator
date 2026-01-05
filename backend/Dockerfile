# Multi-stage build for GPU VRAM Orchestrator

# Stage 1: Builder
FROM pytorch/pytorch:2.1.0-cuda12.1-runtime-ubuntu22.04 as builder

WORKDIR /build

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM pytorch/pytorch:2.1.0-cuda12.1-runtime-ubuntu22.04

WORKDIR /app

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    GPU_ENABLED=true \
    LOG_LEVEL=INFO

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY backend/src ./src
COPY backend/tests ./tests
COPY backend/pytest.ini .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run tests on startup (useful for debugging)
# Production would just run the app
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
