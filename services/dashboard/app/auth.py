"""
Valhalla Capital Dashboard - Authentication

Single-password cookie auth for owner access.
Uses hashlib.scrypt for password hashing and itsdangerous for signed cookies.
"""

import base64
import hashlib
import hmac
import os
import time
from collections import defaultdict

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


# ---------------------------------------------------------------------------
# Password hashing (scrypt)
# ---------------------------------------------------------------------------

def hash_password(plaintext: str) -> str:
    """Hash a password with scrypt. Returns 'salt$hash' (both base64)."""
    salt = os.urandom(16)
    derived = hashlib.scrypt(
        plaintext.encode(), salt=salt, n=16384, r=8, p=1, dklen=32
    )
    salt_b64 = base64.b64encode(salt).decode()
    hash_b64 = base64.b64encode(derived).decode()
    return f"{salt_b64}${hash_b64}"


def verify_password(plaintext: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored 'salt$hash' string."""
    if "$" not in stored_hash:
        return False
    salt_b64, hash_b64 = stored_hash.split("$", 1)
    try:
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except Exception:
        return False
    derived = hashlib.scrypt(
        plaintext.encode(), salt=salt, n=16384, r=8, p=1, dklen=32
    )
    return hmac.compare_digest(derived, expected)


# ---------------------------------------------------------------------------
# Session tokens (signed cookies via itsdangerous)
# ---------------------------------------------------------------------------

def create_session(secret: str) -> str:
    """Create a signed session token."""
    s = URLSafeTimedSerializer(secret)
    return s.dumps({"role": "owner"})


def validate_session(cookie: str, secret: str, max_age: int) -> bool:
    """Validate a signed session cookie. Returns True if valid and not expired."""
    if not cookie or not secret:
        return False
    s = URLSafeTimedSerializer(secret)
    try:
        data = s.loads(cookie, max_age=max_age)
        return isinstance(data, dict) and data.get("role") == "owner"
    except (BadSignature, SignatureExpired):
        return False


# ---------------------------------------------------------------------------
# CSRF tokens
# ---------------------------------------------------------------------------

def create_csrf_token(secret: str) -> str:
    """Create a signed CSRF token (10 min validity)."""
    s = URLSafeTimedSerializer(secret, salt="csrf")
    return s.dumps({"csrf": True})


def validate_csrf_token(token: str, secret: str, max_age: int = 600) -> bool:
    """Validate a CSRF token. Default max_age = 10 minutes."""
    if not token or not secret:
        return False
    s = URLSafeTimedSerializer(secret, salt="csrf")
    try:
        data = s.loads(token, max_age=max_age)
        return isinstance(data, dict) and data.get("csrf") is True
    except (BadSignature, SignatureExpired):
        return False


# ---------------------------------------------------------------------------
# Rate limiter (in-memory)
# ---------------------------------------------------------------------------

_LOGIN_ATTEMPTS: dict[str, tuple[int, float]] = {}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes
_MAX_TRACKED_IPS = 10_000


def _evict_stale_entries() -> None:
    """Remove expired lockouts and cap total tracked IPs."""
    now = time.monotonic()
    stale = [
        ip for ip, (_, locked_until) in _LOGIN_ATTEMPTS.items()
        if locked_until > 0 and now >= locked_until
    ]
    for ip in stale:
        del _LOGIN_ATTEMPTS[ip]
    # Hard cap: drop oldest entries if over limit
    while len(_LOGIN_ATTEMPTS) > _MAX_TRACKED_IPS:
        oldest = next(iter(_LOGIN_ATTEMPTS))
        del _LOGIN_ATTEMPTS[oldest]


def check_rate_limit(ip: str) -> bool:
    """Return True if the IP is allowed to attempt login."""
    _evict_stale_entries()
    record = _LOGIN_ATTEMPTS.get(ip)
    if record is None:
        return True
    count, locked_until = record
    if locked_until > 0 and time.monotonic() < locked_until:
        return False
    if locked_until > 0 and time.monotonic() >= locked_until:
        del _LOGIN_ATTEMPTS[ip]
        return True
    return True


def record_failed_attempt(ip: str) -> None:
    """Record a failed login attempt. Locks out after MAX_ATTEMPTS."""
    record = _LOGIN_ATTEMPTS.get(ip)
    if record is None:
        _LOGIN_ATTEMPTS[ip] = (1, 0)
    else:
        count, _ = record
        new_count = count + 1
        if new_count >= MAX_ATTEMPTS:
            _LOGIN_ATTEMPTS[ip] = (new_count, time.monotonic() + LOCKOUT_SECONDS)
        else:
            _LOGIN_ATTEMPTS[ip] = (new_count, 0)


def clear_failed_attempts(ip: str) -> None:
    """Clear failed attempts on successful login."""
    _LOGIN_ATTEMPTS.pop(ip, None)


# ---------------------------------------------------------------------------
# CLI for generating password hashes
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import getpass
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "hash":
        pw = getpass.getpass("Password: ")
        pw2 = getpass.getpass("Confirm:  ")
        if pw != pw2:
            print("Passwords do not match.")
            sys.exit(1)
        print(f"\nOWNER_PASSWORD_HASH={hash_password(pw)}")
    else:
        print("Usage: python -m app.auth hash")
