# FMP Data Client REST API

A FastAPI-based REST API server for the FMP Data Client library with authentication, rate limiting, and automatic OpenAPI documentation.

## Features

- **FastAPI Framework** - High-performance async API
- **API Key Authentication** - Secure access control via X-API-Key header
- **Rate Limiting** - Per-client rate limiting (configurable)
- **CORS Support** - Cross-origin requests enabled
- **OpenAPI Documentation** - Auto-generated Swagger UI at `/docs`
- **Health Checks** - Monitor API and component status
- **Cache Management** - View stats and clear cache via API

## Installation

Install with server dependencies:

```bash
pip install -e ".[server]"
```

This installs:
- `fastapi` - Web framework
- `uvicorn[standard]` - ASGI server

## Quick Start

### 1. Set Environment Variables

Create a `.env` file:

```env
# Required
FMP_API_KEY=your_fmp_api_key_here

# Optional
FMP_TIER=PREMIUM
MYSQL_HOST=localhost
MYSQL_USER=fmp_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=fmp_cache
ANTHROPIC_API_KEY=your_anthropic_key  # For LLM features

# Server configuration
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=false
API_WORKERS=4
```

### 2. Start the Server

**Option A: Using the startup script**
```bash
python run_server.py
```

**Option B: Using uvicorn directly**
```bash
uvicorn fmp_data_client.server:app --host 0.0.0.0 --port 8000
```

**Option C: With auto-reload for development**
```bash
uvicorn fmp_data_client.server:app --reload
```

The server will start at `http://localhost:8000`

### 3. Access Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Authentication

All endpoints (except `/`, `/health`, and `/docs`) require API key authentication.

### Using the Demo API Key

A demo API key is included for testing:

```bash
curl -H "X-API-Key: demo-api-key-12345" \
  http://localhost:8000/quote/AAPL
```

### Creating New API Keys

```python
from fmp_data_client.server import create_api_key

# Create a new API key
api_key = create_api_key(
    name="Production Client",
    tier="PREMIUM",
    rate_limit=300  # requests per minute
)
print(f"New API key: {api_key}")
```

### Revoking API Keys

```python
from fmp_data_client.server import revoke_api_key

# Revoke an API key
success = revoke_api_key("fmp-...")
```

## Endpoints

### Root & Health

#### `GET /`
Root endpoint with API information.

```bash
curl http://localhost:8000/
```

Response:
```json
{
  "name": "FMP Data Client API",
  "version": "1.0.0",
  "docs": "/docs",
  "health": "/health"
}
```

#### `GET /health`
Health check for API and components.

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-23T10:30:00",
  "components": {
    "api": "healthy",
    "fmp_client": "healthy",
    "cache": "healthy"
  }
}
```

### Stock Data

#### `GET /quote/{symbol}`
Get real-time quote for a stock.

**Parameters:**
- `symbol` (path): Stock ticker symbol

**Headers:**
- `X-API-Key`: Your API key

```bash
curl -H "X-API-Key: demo-api-key-12345" \
  http://localhost:8000/quote/AAPL
```

Response:
```json
{
  "symbol": "AAPL",
  "price": 185.50,
  "change": 2.30,
  "change_percent": 1.25,
  "volume": 55000000,
  "day_high": 186.20,
  "day_low": 183.00,
  "previous_close": 183.20,
  "market_cap": 2850000000000,
  "timestamp": 1705951200
}
```

#### `GET /profile/{symbol}`
Get company profile.

```bash
curl -H "X-API-Key: demo-api-key-12345" \
  http://localhost:8000/profile/AAPL
```

Response:
```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "description": "Apple Inc. designs, manufactures...",
  "ceo": "Timothy Cook",
  "employees": 164000,
  "website": "https://www.apple.com",
  "country": "US",
  "market_cap": 2850000000000,
  "exchange": "NASDAQ"
}
```

#### `POST /ticker`
Get comprehensive ticker data based on custom request.

**Headers:**
- `X-API-Key`: Your API key
- `Content-Type`: application/json

**Body:** DataRequest JSON

```bash
curl -X POST \
  -H "X-API-Key: demo-api-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "include_quote": true,
    "include_profile": true,
    "include_fundamentals": true,
    "fundamentals_periods": 4
  }' \
  http://localhost:8000/ticker
```

Response:
```json
{
  "symbol": "AAPL",
  "data": {
    "symbol": "AAPL",
    "quote": {...},
    "profile": {...},
    "income_statements": [...],
    "balance_sheets": [...],
    "cash_flow_statements": [...]
  },
  "cached": false,
  "fetched_at": "2024-01-23T10:30:00"
}
```

### Cache Management

#### `GET /cache/status`
Get cache statistics.

```bash
curl -H "X-API-Key: demo-api-key-12345" \
  http://localhost:8000/cache/status
```

Response:
```json
{
  "enabled": true,
  "total_entries": 1523,
  "hit_rate": 0.87,
  "stats": {
    "total_entries": 1523,
    "ticker_data_count": 856,
    "transcripts_count": 234,
    "filing_summaries_count": 433,
    "hit_rate": 0.87
  }
}
```

#### `POST /cache/clear`
Clear all cached data.

```bash
curl -X POST \
  -H "X-API-Key: demo-api-key-12345" \
  http://localhost:8000/cache/clear
```

Response:
```json
{
  "success": true,
  "message": "Cache cleared successfully"
}
```

## Rate Limiting

All responses include rate limit headers:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 2024-01-23T10:31:00
```

When limit exceeded (HTTP 429):
```json
{
  "error": "Rate limit exceeded",
  "detail": "Limit: 60 requests/minute. Try again after 2024-01-23T10:31:00",
  "status_code": 429
}
```

## Error Handling

All errors follow a consistent format:

```json
{
  "error": "Error message",
  "detail": "Detailed error information",
  "status_code": 400
}
```

**Common status codes:**
- `400` - Bad Request (invalid parameters)
- `401` - Unauthorized (missing/invalid API key)
- `403` - Forbidden (API key disabled)
- `404` - Not Found (symbol not found)
- `429` - Too Many Requests (rate limit exceeded)
- `500` - Internal Server Error

## Production Deployment

### Using Gunicorn + Uvicorn

```bash
gunicorn fmp_data_client.server:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Using Docker

See `Dockerfile` and `docker-compose.yml` for containerized deployment.

### Environment Variables

Production configuration:

```env
# FMP Configuration
FMP_API_KEY=your_production_key
FMP_TIER=ULTIMATE
FMP_CACHE_ENABLED=true

# MySQL Cache (recommended for production)
MYSQL_HOST=mysql-server
MYSQL_PORT=3306
MYSQL_USER=fmp_user
MYSQL_PASSWORD=secure_password
MYSQL_DATABASE=fmp_cache
MYSQL_POOL_SIZE=10

# LLM Summarization (optional)
ANTHROPIC_API_KEY=your_key
FMP_SUMMARIZATION_ENABLED=true
FMP_DEFAULT_MODEL=claude-3-haiku-20240307

# Server Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
API_RELOAD=false
```

### Security Best Practices

1. **Use HTTPS** in production with proper SSL certificates
2. **Configure CORS** appropriately (don't use `allow_origins=["*"]`)
3. **Store API keys securely** in database with hashing
4. **Use rate limiting** to prevent abuse
5. **Monitor logs** for suspicious activity
6. **Set up health checks** for load balancers
7. **Use environment variables** for secrets (never commit)

### Load Balancing

The API is stateless and can be horizontally scaled:

```bash
# Start multiple workers
uvicorn fmp_data_client.server:app --workers 8

# Or use a load balancer (nginx, HAProxy, etc.)
upstream fmp_api {
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
    server 127.0.0.1:8003;
    server 127.0.0.1:8004;
}
```

## Integration Examples

### Python Client

```python
import requests

API_URL = "http://localhost:8000"
API_KEY = "demo-api-key-12345"

headers = {
    "X-API-Key": API_KEY,
}

# Get quote
response = requests.get(f"{API_URL}/quote/AAPL", headers=headers)
quote = response.json()
print(f"AAPL Price: ${quote['price']}")

# Get comprehensive data
data_request = {
    "symbol": "MSFT",
    "include_quote": True,
    "include_profile": True,
    "include_fundamentals": True,
    "fundamentals_periods": 4,
}
response = requests.post(
    f"{API_URL}/ticker",
    json=data_request,
    headers=headers
)
ticker_data = response.json()
```

### JavaScript/TypeScript

```typescript
const API_URL = 'http://localhost:8000';
const API_KEY = 'demo-api-key-12345';

async function getQuote(symbol: string) {
  const response = await fetch(`${API_URL}/quote/${symbol}`, {
    headers: {
      'X-API-Key': API_KEY,
    },
  });
  return response.json();
}

const quote = await getQuote('AAPL');
console.log(`AAPL Price: $${quote.price}`);
```

### cURL

```bash
# Save API key for reuse
export API_KEY="demo-api-key-12345"

# Get quote
curl -H "X-API-Key: $API_KEY" \
  http://localhost:8000/quote/AAPL

# Get profile
curl -H "X-API-Key: $API_KEY" \
  http://localhost:8000/profile/AAPL | jq

# Check health
curl http://localhost:8000/health | jq
```

## Development

### Running Tests

```bash
pytest tests/test_server.py -v
```

### API Documentation

The API automatically generates OpenAPI 3.0 documentation:
- Interactive Swagger UI: http://localhost:8000/docs
- ReDoc documentation: http://localhost:8000/redoc
- OpenAPI JSON schema: http://localhost:8000/openapi.json

### Adding New Endpoints

1. Add endpoint function in `server/api.py`
2. Add response model in `server/models.py` (if needed)
3. Update `server/__init__.py` exports
4. Add tests in `tests/test_server.py`
5. Update this documentation

## Monitoring

### Logs

Enable detailed logging:

```bash
uvicorn fmp_data_client.server:app \
  --log-level debug \
  --access-log
```

### Metrics

Consider integrating:
- Prometheus metrics
- DataDog/New Relic APM
- Sentry error tracking
- Custom health check endpoints

## Troubleshooting

**Server won't start:**
- Check if port 8000 is already in use
- Verify FMP_API_KEY is set
- Check Python version (requires 3.11+)

**Authentication errors:**
- Verify X-API-Key header is included
- Check API key is valid and enabled
- Ensure API key has proper permissions

**Rate limit issues:**
- Increase rate_limit for your API key
- Implement client-side throttling
- Use caching to reduce requests

**Cache issues:**
- Verify MySQL connection if cache enabled
- Check cache configuration in .env
- Clear cache if stale data

## Support

For issues and questions:
- GitHub Issues: https://github.com/evangelinekamin/FMP-Access-Library/issues
- Documentation: See README.md and code docstrings
- OpenAPI Docs: http://localhost:8000/docs
