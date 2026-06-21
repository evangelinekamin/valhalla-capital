#!/usr/bin/env python3
"""Initialize database with TimescaleDB extension."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from config.settings import Settings


def main():
    """Initialize database."""
    settings = Settings()

    print("Connecting to database...")
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        # Enable TimescaleDB extension
        print("Enabling TimescaleDB extension...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
        conn.commit()

        print("✓ Database initialized")

    print()
    print("Next steps:")
    print("1. Run migrations: alembic upgrade head")
    print("2. Start trading service: docker-compose up -d trading-service")


if __name__ == "__main__":
    main()
