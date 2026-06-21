# Docker Deployment Guide

Complete guide for deploying FMP Data Client using Docker and docker-compose.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Building and Running](#building-and-running)
- [Services](#services)
- [Environment Variables](#environment-variables)
- [Production Deployment](#production-deployment)
- [Scaling](#scaling)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Maintenance](#maintenance)

## Quick Start

Get the API server and MySQL cache running in under 2 minutes:

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env and set your API keys
nano .env  # Set FMP_API_KEY and optionally ANTHROPIC_API_KEY

# 3. Start all services
docker-compose up -d

# 4. Check health
curl http://localhost:8000/health

# 5. View logs
docker-compose logs -f api
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

## Prerequisites

- **Docker**: Version 20.10 or higher
- **Docker Compose**: Version 2.0 or higher
- **FMP API Key**: Get one at [Financial Modeling Prep](https://financialmodelingprep.com)
- **System Requirements**:
  - 2GB RAM minimum (4GB recommended)
  - 10GB disk space
  - Linux, macOS, or Windows with WSL2

### Installation

**Linux (Ubuntu/Debian)**:
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt-get install docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

**macOS**:
```bash
# Install Docker Desktop
brew install --cask docker
```

**Windows**:
Download Docker Desktop from [docker.com](https://www.docker.com/products/docker-desktop)

## Configuration

### Environment File

Create `.env` from template:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Required: FMP API credentials
FMP_API_KEY=your_actual_api_key_here
FMP_TIER=PREMIUM  # STARTER, PREMIUM, or ULTIMATE

# MySQL credentials (change in production!)
MYSQL_ROOT_PASSWORD=secure_root_password_change_me
MYSQL_PASSWORD=secure_password_change_me
MYSQL_USER=fmp_user
MYSQL_DATABASE=fmp_cache

# Optional: LLM Summarization
FMP_SUMMARIZATION_ENABLED=true
ANTHROPIC_API_KEY=your_anthropic_key_here

# API Server
API_PORT=8000
API_WORKERS=4

# Rate Limiting (adjust based on FMP tier)
FMP_CALLS_PER_MINUTE=750  # PREMIUM tier default
FMP_MAX_CONCURRENT_REQUESTS=20
```

### Docker Compose Override (Optional)

For development customization, create `docker-compose.override.yml`:

```yaml
version: '3.8'

services:
  api:
    volumes:
      # Mount source for hot reload
      - ./fmp_data_client:/app/fmp_data_client
    environment:
      API_RELOAD: "true"
    command: >
      uvicorn fmp_data_client.server:app
      --host 0.0.0.0
      --port 8000
      --reload

  mysql:
    ports:
      # Expose MySQL for local debugging
      - "3307:3306"
```

## Building and Running

### Development Mode

```bash
# Start all services in foreground
docker-compose up

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f api
docker-compose logs -f mysql

# Stop all services
docker-compose down

# Stop and remove volumes (deletes cache!)
docker-compose down -v
```

### Production Mode

```bash
# Build images with no cache
docker-compose build --no-cache

# Start with restart policy
docker-compose up -d --force-recreate

# Check status
docker-compose ps

# Verify health
curl http://localhost:8000/health
```

## Services

### API Service

- **Image**: Custom built from `Dockerfile`
- **Port**: 8000 (configurable via `API_PORT`)
- **Restart**: `unless-stopped`
- **Health Check**: GET `/health` every 30s
- **Dependencies**: MySQL (waits for healthy status)

**Service commands**:
```bash
# Restart API only
docker-compose restart api

# View API logs
docker-compose logs -f api

# Execute command in API container
docker-compose exec api python -c "from fmp_data_client import FMPDataClient; print('OK')"

# Get shell access
docker-compose exec api /bin/bash
```

### MySQL Service

- **Image**: `mysql:8.0`
- **Port**: 3306 (mapped to host)
- **Volume**: `mysql_data` (persistent storage)
- **Init Script**: `docker/mysql/init.sql`
- **Health Check**: `mysqladmin ping` every 10s

**Service commands**:
```bash
# Restart MySQL only
docker-compose restart mysql

# View MySQL logs
docker-compose logs -f mysql

# Connect to MySQL CLI
docker-compose exec mysql mysql -u fmp_user -p fmp_cache

# Backup database
docker-compose exec mysql mysqldump -u root -p fmp_cache > backup.sql

# Restore database
docker-compose exec -T mysql mysql -u root -p fmp_cache < backup.sql
```

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `FMP_API_KEY` | Your FMP API key | `abc123...` |
| `MYSQL_ROOT_PASSWORD` | MySQL root password | `secure_root_pw` |
| `MYSQL_PASSWORD` | App user password | `secure_app_pw` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FMP_TIER` | `STARTER` | FMP subscription tier |
| `FMP_CACHE_ENABLED` | `true` | Enable MySQL caching |
| `FMP_SUMMARIZATION_ENABLED` | `false` | Enable LLM summaries |
| `ANTHROPIC_API_KEY` | - | Claude API key |
| `API_PORT` | `8000` | API server port |
| `API_WORKERS` | `4` | Uvicorn workers |
| `API_RELOAD` | `false` | Hot reload (dev only) |
| `FMP_CALLS_PER_MINUTE` | `300` | Rate limit |
| `LOG_LEVEL` | `INFO` | Logging level |

## Production Deployment

### Security Checklist

Before deploying to production:

- [ ] Change all default passwords in `.env`
- [ ] Use strong, randomly generated passwords (20+ characters)
- [ ] Store `.env` securely (never commit to git)
- [ ] Enable HTTPS via reverse proxy (nginx, Traefik)
- [ ] Configure firewall rules (only expose necessary ports)
- [ ] Disable MySQL port exposure (remove from docker-compose.yml)
- [ ] Set up proper API key management (not using demo keys)
- [ ] Configure CORS properly (restrict allowed origins)
- [ ] Enable log aggregation (ELK, Datadog)
- [ ] Set up monitoring and alerting
- [ ] Configure automated backups
- [ ] Use Docker secrets for sensitive data (Swarm/Kubernetes)

### Reverse Proxy with Nginx

Example nginx configuration for HTTPS termination:

```nginx
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/ssl/certs/yourdomain.crt;
    ssl_certificate_key /etc/ssl/private/yourdomain.key;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Docker Compose Production Settings

Update `docker-compose.yml` for production:

```yaml
services:
  api:
    restart: always  # Changed from unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G

  mysql:
    restart: always
    # Remove ports section - don't expose MySQL externally
    command: >
      --default-authentication-plugin=mysql_native_password
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_unicode_ci
      --max-connections=200
      --innodb-buffer-pool-size=1G
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Automated Backups

Create backup script `backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/backups/mysql"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

docker-compose exec -T mysql mysqldump \
    -u root \
    -p"$MYSQL_ROOT_PASSWORD" \
    --all-databases \
    --single-transaction \
    --quick \
    --lock-tables=false \
    > "$BACKUP_DIR/fmp_backup_$DATE.sql"

# Compress backup
gzip "$BACKUP_DIR/fmp_backup_$DATE.sql"

# Keep only last 7 days
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

echo "Backup completed: fmp_backup_$DATE.sql.gz"
```

Add to crontab:
```bash
# Daily backup at 2 AM
0 2 * * * /path/to/backup.sh >> /var/log/fmp_backup.log 2>&1
```

## Scaling

### Horizontal Scaling (Multiple API Instances)

Update `docker-compose.yml` to run multiple API instances:

```yaml
services:
  api:
    deploy:
      replicas: 3  # Run 3 API instances

  # Add load balancer
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - api
```

Example `nginx.conf`:
```nginx
upstream api_backend {
    least_conn;
    server api:8000;
}

server {
    listen 80;
    location / {
        proxy_pass http://api_backend;
    }
}
```

### Vertical Scaling (Resource Limits)

Adjust resource limits in `docker-compose.yml`:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '4.0'      # Increase CPU
          memory: 4G       # Increase RAM
    environment:
      API_WORKERS: 8       # More workers
```

## Monitoring

### Health Checks

Built-in health endpoints:

```bash
# API health
curl http://localhost:8000/health

# Cache status
curl -H "X-API-Key: your-api-key" http://localhost:8000/cache/status

# MySQL health
docker-compose exec mysql mysqladmin ping -h localhost -u root -p
```

### Docker Stats

Monitor resource usage:

```bash
# All containers
docker stats

# Specific service
docker stats fmp-api fmp-mysql

# JSON output for parsing
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### Logs

```bash
# Tail logs
docker-compose logs -f --tail=100

# Search logs
docker-compose logs api | grep ERROR

# Export logs
docker-compose logs --no-color > logs_$(date +%Y%m%d).txt
```

### Prometheus Metrics (Optional)

Add Prometheus and Grafana for advanced monitoring:

```yaml
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
```

## Troubleshooting

### Common Issues

#### 1. API won't start - "Connection refused" to MySQL

**Symptom**: API logs show `Can't connect to MySQL server`

**Solution**:
```bash
# Check MySQL is healthy
docker-compose ps

# Wait for MySQL to be ready
docker-compose up -d mysql
docker-compose logs -f mysql  # Wait for "ready for connections"

# Then start API
docker-compose up -d api
```

#### 2. Port already in use

**Symptom**: `Error starting userland proxy: listen tcp 0.0.0.0:8000: bind: address already in use`

**Solution**:
```bash
# Find what's using the port
sudo lsof -i :8000

# Kill the process or change API_PORT in .env
echo "API_PORT=8001" >> .env
docker-compose up -d
```

#### 3. MySQL data not persisting

**Symptom**: Cache is empty after restart

**Solution**:
```bash
# Check volume exists
docker volume ls | grep mysql

# Inspect volume
docker volume inspect fmp-access-library_mysql_data

# If missing, recreate
docker-compose down
docker-compose up -d
```

#### 4. Permission denied errors

**Symptom**: `Permission denied` in container logs

**Solution**:
```bash
# Fix file permissions
sudo chown -R 1000:1000 .

# Rebuild image
docker-compose build --no-cache api
docker-compose up -d
```

#### 5. Out of memory

**Symptom**: Container killed, exit code 137

**Solution**:
```bash
# Check Docker memory limits
docker info | grep Memory

# Increase limits in docker-compose.yml
# Or reduce API_WORKERS in .env
```

### Debug Mode

Enable verbose logging:

```bash
# Set log level
echo "LOG_LEVEL=DEBUG" >> .env

# Restart services
docker-compose restart api

# Watch debug logs
docker-compose logs -f api
```

### Container Shell Access

Debug inside containers:

```bash
# API container
docker-compose exec api /bin/bash

# MySQL container
docker-compose exec mysql /bin/bash

# As root user
docker-compose exec -u root api /bin/bash
```

## Maintenance

### Updating

```bash
# Pull latest code
git pull

# Rebuild images
docker-compose build --pull --no-cache

# Restart with new images
docker-compose up -d --force-recreate

# Clean up old images
docker image prune -f
```

### Cleaning Up

```bash
# Remove stopped containers
docker-compose down

# Remove volumes (WARNING: deletes cache data!)
docker-compose down -v

# Clean up old images
docker image prune -a

# Full cleanup (use with caution)
docker system prune -a --volumes
```

### Database Maintenance

```bash
# Optimize tables
docker-compose exec mysql mysql -u root -p -e "
USE fmp_cache;
OPTIMIZE TABLE api_cache;
OPTIMIZE TABLE cache_stats;
"

# Clean expired cache manually
docker-compose exec mysql mysql -u root -p -e "
USE fmp_cache;
CALL cleanup_expired_cache();
"

# Check database size
docker-compose exec mysql mysql -u root -p -e "
SELECT
    table_schema AS 'Database',
    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)'
FROM information_schema.tables
WHERE table_schema = 'fmp_cache'
GROUP BY table_schema;
"
```

## Advanced Topics

### Using Docker Swarm

Deploy to Docker Swarm cluster:

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml fmp

# Scale services
docker service scale fmp_api=5

# Update service
docker service update fmp_api --image fmp-api:latest
```

### Using Kubernetes

Convert to Kubernetes with Kompose:

```bash
# Install kompose
curl -L https://github.com/kubernetes/kompose/releases/download/v1.26.1/kompose-linux-amd64 -o kompose
chmod +x kompose
sudo mv kompose /usr/local/bin/

# Convert docker-compose to k8s
kompose convert -f docker-compose.yml

# Deploy to k8s
kubectl apply -f .
```

### CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Build and push
        run: |
          docker build -t your-registry/fmp-api:${{ github.sha }} .
          docker push your-registry/fmp-api:${{ github.sha }}

      - name: Deploy
        run: |
          ssh user@server "cd /opt/fmp && docker-compose pull && docker-compose up -d"
```

## Support

- **Documentation**: See `REST_API.md` for API details
- **Issues**: Report at GitHub repository
- **Logs**: Check `docker-compose logs` for errors

## Summary

This deployment provides:
- ✅ Production-ready Docker setup
- ✅ MySQL cache with automatic initialization
- ✅ Health checks and auto-restart
- ✅ Horizontal and vertical scaling options
- ✅ Security best practices
- ✅ Monitoring and logging
- ✅ Backup and maintenance procedures

The entire stack can be deployed with a single command: `docker-compose up -d`
