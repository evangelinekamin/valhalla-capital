#!/usr/bin/env python3
"""Health check script for trading service container."""
import os
import sys


def check_database():
    """Check database connectivity."""
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(os.environ["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"Database check failed: {e}")
        return False


def check_ibkr():
    """Check IBKR connection."""
    try:
        from ib_insync import IB

        ib = IB()
        ib.connect(
            os.environ.get("IBKR_HOST", "ib-gateway"),
            int(os.environ.get("IBKR_PORT", 4002)),
            clientId=999,  # Use different client ID for health check
            timeout=5,
        )
        connected = ib.isConnected()
        ib.disconnect()
        return connected
    except Exception as e:
        print(f"IBKR check failed: {e}")
        return False


def check_file_system():
    """Check shared volume access."""
    try:
        from pathlib import Path

        requests_path = Path(os.environ.get("TRADE_REQUESTS_PATH", "/shared/trade_requests"))
        return requests_path.exists() and requests_path.is_dir()
    except Exception as e:
        print(f"File system check failed: {e}")
        return False


def main():
    """Run all health checks."""
    checks = {
        "database": check_database(),
        "ibkr": check_ibkr(),
        "file_system": check_file_system(),
    }

    all_passed = all(checks.values())

    if all_passed:
        print("Health check passed")
        sys.exit(0)
    else:
        failed = [name for name, passed in checks.items() if not passed]
        print(f"Health check failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
