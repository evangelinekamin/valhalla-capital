# Multi-stage build for FMP Data Client API Server
# Stage 1: Builder - Install dependencies
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies to /install directory
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime - Minimal image with only runtime dependencies
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only (MySQL client)
RUN apt-get update && apt-get install -y \
    default-mysql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user for security
RUN useradd -m -u 1000 fmpuser && \
    chown -R fmpuser:fmpuser /app

# Copy application code
COPY --chown=fmpuser:fmpuser fmp_data_client/ ./fmp_data_client/
COPY --chown=fmpuser:fmpuser run_server.py .
COPY --chown=fmpuser:fmpuser pyproject.toml .

# Switch to non-root user
USER fmpuser

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000

# Run the server
CMD ["python", "run_server.py"]
