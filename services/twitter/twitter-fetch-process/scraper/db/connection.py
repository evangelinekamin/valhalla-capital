"""
Database connection management for the Twitter monitoring system.

This module provides:
- Database configuration from environment variables
- Connection pooling with a cached singleton engine
- Session management with context managers
- Error handling for connection failures

Environment Variables:
    DB_HOST: Database host (default: localhost)
    DB_PORT: Database port (default: 5432)
    DB_NAME: Database name (default: twitter_data)
    DB_USER: Database user (default: postgres)
    DB_PASSWORD: Database password (default: empty)
"""

import logging
import os
from dataclasses import dataclass
from contextlib import contextmanager
from typing import Optional, Generator
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from .schema import Base, create_gin_index

logger = logging.getLogger(__name__)

# Module-level cached engine (singleton)
_engine: Optional[Engine] = None


@dataclass
class DatabaseConfig:
    """
    Database configuration container.

    Reads configuration from environment variables with sensible defaults.
    Handles URL encoding for special characters in passwords.
    """

    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """
        Create configuration from environment variables.

        Returns:
            DatabaseConfig instance with values from environment
        """
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "twitter_data"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        )

    @property
    def connection_string(self) -> str:
        """
        Generate PostgreSQL connection string.

        Handles URL encoding for special characters in password.

        Returns:
            PostgreSQL connection URL
        """
        # URL-encode password to handle special characters
        encoded_password = quote_plus(self.password) if self.password else ""

        return (
            f"postgresql://{self.user}:{encoded_password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


def get_engine(
    connection_string: Optional[str] = None,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_timeout: int = 30,
    pool_recycle: int = 1800,
    echo: bool = False,
) -> Engine:
    """
    Get or create a SQLAlchemy engine with connection pooling.

    Uses a module-level cached engine when called without arguments,
    so all callers share the same connection pool.

    Args:
        connection_string: Database connection URL. If None, auto-creates
            from environment variables and caches the result.
        pool_size: Number of connections to keep in pool (default: 5)
        max_overflow: Max connections beyond pool_size (default: 10)
        pool_timeout: Seconds to wait for connection (default: 30)
        pool_recycle: Seconds before recycling connection (default: 1800)
        echo: Whether to log SQL statements (default: False)

    Returns:
        SQLAlchemy Engine instance
    """
    global _engine

    # When no connection string is provided, use/create the cached engine
    if connection_string is None:
        if _engine is not None:
            return _engine
        config = DatabaseConfig.from_env()
        connection_string = config.connection_string
        logger.info(f"Creating database engine for {config.host}:{config.port}/{config.database}")

    # SQLite doesn't support pool configuration
    if connection_string.startswith("sqlite"):
        engine = create_engine(connection_string, echo=echo)
    else:
        engine = create_engine(
            connection_string,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            echo=echo,
        )

    # Cache the engine for future calls without arguments
    if _engine is None:
        _engine = engine

    return engine


def get_session(engine: Optional[Engine] = None) -> Session:
    """
    Create a new database session.

    Args:
        engine: SQLAlchemy engine (defaults to cached engine)

    Returns:
        New Session instance

    Note:
        Caller is responsible for closing the session.
    """
    if engine is None:
        engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@contextmanager
def session_scope(engine: Optional[Engine] = None) -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Provides automatic commit on success and rollback on error.

    Args:
        engine: SQLAlchemy engine (defaults to cached engine)

    Yields:
        Session instance

    Example:
        with session_scope() as session:
            tweet = Tweet(miniflux_id=123)
            session.add(tweet)
        # Auto-committed on success

    Raises:
        Exception: Re-raises any exception after rollback
    """
    session = get_session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_tables(engine: Engine) -> None:
    """
    Create all database tables.

    Idempotent - safe to call multiple times.

    Args:
        engine: SQLAlchemy engine

    Note:
        For PostgreSQL, also creates GIN index for tickers array.
    """
    Base.metadata.create_all(engine)

    # Create PostgreSQL-specific indexes
    if engine.dialect.name == "postgresql":
        create_gin_index(engine)


def init_database(config: Optional[DatabaseConfig] = None) -> Engine:
    """
    Initialize database with configuration.

    Convenience function that:
    1. Loads config from environment if not provided
    2. Creates engine with pooling (cached for reuse)
    3. Creates all tables

    Args:
        config: Optional DatabaseConfig (defaults to from_env())

    Returns:
        Configured Engine instance
    """
    if config is None:
        engine = get_engine()
    else:
        engine = get_engine(config.connection_string)

    create_tables(engine)
    return engine
