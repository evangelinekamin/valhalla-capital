"""API authentication and authorization."""

import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import mysql.connector
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

# API key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# MySQL connection for API key storage
def get_db_connection():
    """Get MySQL database connection for API keys."""
    return mysql.connector.connect(
        host=os.getenv("FMP_MYSQL_HOST", "mysql"),
        port=int(os.getenv("FMP_MYSQL_PORT", "3306")),
        user=os.getenv("FMP_MYSQL_USER", "fmp_user"),
        password=os.getenv("FMP_MYSQL_PASSWORD"),
        database=os.getenv("FMP_MYSQL_DATABASE", "fmp_cache"),
    )

# Rate limiting storage: {api_key: {window_start: timestamp, count: int}}
RATE_LIMIT_STORAGE: Dict[str, Dict] = {}


def validate_api_key(api_key: Optional[str] = Security(api_key_header)) -> Dict:
    """Validate API key and return key metadata.

    Args:
        api_key: API key from request header

    Returns:
        API key metadata

    Raises:
        HTTPException: If API key is invalid or disabled
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required. Provide it in X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM api_keys WHERE api_key = %s",
            (api_key,)
        )
        key_data = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )

    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not key_data.get("enabled", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key has been disabled",
        )

    return key_data


def check_rate_limit(api_key: str, key_data: Dict) -> None:
    """Check and enforce rate limiting for API key.

    Args:
        api_key: API key string
        key_data: API key metadata

    Raises:
        HTTPException: If rate limit exceeded
    """
    rate_limit = key_data.get("rate_limit", 60)
    now = datetime.now()
    window_duration = timedelta(minutes=1)

    # Get or create rate limit tracking for this key
    if api_key not in RATE_LIMIT_STORAGE:
        RATE_LIMIT_STORAGE[api_key] = {
            "window_start": now,
            "count": 0,
        }

    rate_data = RATE_LIMIT_STORAGE[api_key]

    # Check if we're in a new window
    window_start = rate_data["window_start"]
    if now - window_start > window_duration:
        # Reset to new window
        rate_data["window_start"] = now
        rate_data["count"] = 0

    # Check rate limit
    if rate_data["count"] >= rate_limit:
        reset_at = (window_start + window_duration).isoformat()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Limit: {rate_limit} requests/minute. Try again after {reset_at}",
            headers={
                "X-RateLimit-Limit": str(rate_limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": reset_at,
            },
        )

    # Increment counter
    rate_data["count"] += 1


def get_rate_limit_headers(api_key: str, key_data: Dict) -> Dict[str, str]:
    """Get rate limit headers for response.

    Args:
        api_key: API key string
        key_data: API key metadata

    Returns:
        Dictionary of rate limit headers
    """
    rate_limit = key_data.get("rate_limit", 60)

    if api_key not in RATE_LIMIT_STORAGE:
        return {
            "X-RateLimit-Limit": str(rate_limit),
            "X-RateLimit-Remaining": str(rate_limit),
        }

    rate_data = RATE_LIMIT_STORAGE[api_key]
    remaining = max(0, rate_limit - rate_data["count"])
    window_start = rate_data["window_start"]
    reset_at = (window_start + timedelta(minutes=1)).isoformat()

    return {
        "X-RateLimit-Limit": str(rate_limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": reset_at,
    }


def create_api_key(name: str, tier: str = "STARTER", rate_limit: int = 60) -> str:
    """Create a new API key.

    Args:
        name: Client name
        tier: API tier (STARTER/PREMIUM/ULTIMATE)
        rate_limit: Rate limit in requests per minute

    Returns:
        Generated API key
    """
    import secrets

    api_key = f"fmp-{secrets.token_urlsafe(32)}"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO api_keys (api_key, name, tier, rate_limit, enabled)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (api_key, name, tier, rate_limit, True)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        raise Exception(f"Failed to create API key: {str(e)}")

    return api_key


def revoke_api_key(api_key: str) -> bool:
    """Revoke an API key.

    Args:
        api_key: API key to revoke

    Returns:
        True if key was revoked, False if not found
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE api_keys SET enabled = FALSE WHERE api_key = %s",
            (api_key,)
        )
        rows_affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        return rows_affected > 0
    except Exception:
        return False
