FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    sqlite3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch first so sentence-transformers doesn't pull the GPU build
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

RUN pip install --no-cache-dir \
    "anthropic>=0.39.0" \
    "asyncpg>=0.29.0" \
    "pgvector>=0.3.0" \
    "pydantic>=2.0" \
    "pydantic-settings>=2.0" \
    "apscheduler>=3.10" \
    "httpx>=0.27" \
    "discord.py>=2.3" \
    "structlog>=24.0" \
    "sentence-transformers>=3.0" \
    "numpy>=1.26" \
    "python-dotenv>=1.0" \
    "beautifulsoup4>=4.12" \
    "lxml>=5.0"

COPY src/overseer ./overseer

# SSH knownhosts dir + accept-new on first connect to host.docker.internal
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "overseer.main"]
