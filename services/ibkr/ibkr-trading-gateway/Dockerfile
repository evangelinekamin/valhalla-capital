FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

# Copy application code
COPY . .

# Create data directory for panic state
RUN mkdir -p /app/data

# Health check script
COPY scripts/health_check.py /health_check.py
RUN chmod +x /health_check.py

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python /health_check.py || exit 1

# Run application
CMD ["python", "-m", "src.main"]
