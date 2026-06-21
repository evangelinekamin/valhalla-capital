from datetime import datetime
from typing import Optional
import logging
import threading

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.connection import get_engine, get_session
from .models import (
    TweetResponse,
    TweetListResponse,
    StatsResponse,
    HealthResponse
)
from .handlers import get_tweets, get_tweet_by_id, get_stats

logger = logging.getLogger(__name__)

# Shared processing status (updated by the processing thread in main.py)
_processing_status = {
    "active": False,
    "last_run_at": None,
    "last_error": None,
    "run_count": 0,
}
_processing_lock = threading.Lock()


def update_processing_status(**kwargs):
    """Thread-safe update of processing status from the monitoring loop."""
    with _processing_lock:
        _processing_status.update(kwargs)


def get_processing_status() -> dict:
    """Thread-safe read of processing status."""
    with _processing_lock:
        return dict(_processing_status)


# Create FastAPI app
app = FastAPI(
    title="Twitter Monitoring API",
    description="API for accessing classified and analyzed Twitter data",
    version="1.0.0"
)

# CORS configuration - restricted to known LXC network
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://<LAN_IP>",  # dashboard LXC
        "http://<LAN_IP>",  # data-collection LXC (local)
        "http://localhost",
    ],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Database dependency
def get_db():
    """Get database session dependency."""
    engine = get_engine()
    db = get_session(engine)
    try:
        yield db
    finally:
        db.close()


@app.get("/", response_model=dict)
async def root():
    """Root endpoint."""
    return {
        "message": "Twitter Monitoring API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "tweets": "/tweets",
            "tweet_by_id": "/tweets/{id}",
            "stats": "/stats"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint.

    Returns system health status including database connectivity
    and processing thread status.
    """
    database_connected = False

    try:
        db.execute(text("SELECT 1"))
        database_connected = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")

    proc_status = get_processing_status()

    return HealthResponse(
        status="healthy" if database_connected else "unhealthy",
        timestamp=datetime.now(),
        database_connected=database_connected,
        processing_active=proc_status["active"],
        last_run_at=proc_status.get("last_run_at"),
        run_count=proc_status.get("run_count", 0),
    )


@app.get("/tweets", response_model=TweetListResponse)
async def list_tweets(
    classification: Optional[str] = Query(
        None,
        description="Filter by classification (CRITICAL, IMPORTANT, ROUTINE, SKIP)"
    ),
    username: Optional[str] = Query(
        None,
        description="Filter by username (partial match)"
    ),
    sentiment: Optional[str] = Query(
        None,
        description="Filter by sentiment (bullish, bearish, neutral)"
    ),
    ticker: Optional[str] = Query(
        None,
        description="Filter by ticker symbol"
    ),
    min_confidence: Optional[float] = Query(
        None,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score (0.0-1.0)"
    ),
    limit: int = Query(
        10,
        ge=1,
        le=100,
        description="Number of results to return"
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of results to skip"
    ),
    db: Session = Depends(get_db)
):
    """
    Get tweets with optional filtering and pagination.

    Examples:
    - /tweets?classification=CRITICAL&limit=10
    - /tweets?username=elonmusk&sentiment=bullish
    - /tweets?ticker=AAPL&min_confidence=0.8
    """
    try:
        # Validate classification
        if classification and classification.upper() not in ['CRITICAL', 'IMPORTANT', 'ROUTINE', 'SKIP']:
            raise HTTPException(
                status_code=400,
                detail="Invalid classification. Must be CRITICAL, IMPORTANT, ROUTINE, or SKIP"
            )

        # Validate sentiment
        if sentiment and sentiment.lower() not in ['bullish', 'bearish', 'neutral']:
            raise HTTPException(
                status_code=400,
                detail="Invalid sentiment. Must be bullish, bearish, or neutral"
            )

        result = get_tweets(
            session=db,
            classification=classification,
            username=username,
            sentiment=sentiment,
            ticker=ticker,
            min_confidence=min_confidence,
            limit=limit,
            offset=offset
        )

        logger.info(
            f"GET /tweets - filters: classification={classification}, "
            f"username={username}, sentiment={sentiment}, ticker={ticker}, "
            f"min_confidence={min_confidence}, limit={limit}, offset={offset} - "
            f"returned {len(result.tweets)} tweets"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing tweets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tweets/{tweet_id}", response_model=TweetResponse)
async def get_tweet(
    tweet_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific tweet by ID.

    Args:
        tweet_id: Tweet ID

    Returns:
        Tweet details with all fields
    """
    try:
        tweet = get_tweet_by_id(db, tweet_id)

        if not tweet:
            raise HTTPException(status_code=404, detail=f"Tweet {tweet_id} not found")

        logger.info(f"GET /tweets/{tweet_id} - success")
        return tweet

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tweet {tweet_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats", response_model=StatsResponse)
async def get_statistics(db: Session = Depends(get_db)):
    """
    Get overall statistics.

    Returns:
    - Total tweet counts
    - Classification breakdown
    - Sentiment breakdown
    - Pre-filter effectiveness
    - Top tickers
    - Top users
    """
    try:
        stats = get_stats(db)

        logger.info("GET /stats - success")
        return stats

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
