FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (exclude dev/test files via .dockerignore)
COPY . .

ENV PYTHONUNBUFFERED=1

# Create non-root user
RUN useradd -m -u 1000 scraper && chown -R scraper:scraper /app
USER scraper

# Expose API port
EXPOSE 8082

# Default command (can be overridden in docker-compose)
CMD ["python", "main.py"]
