from typing import List, Optional, Dict, Any
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from db.schema import Tweet
from .models import (
    TweetResponse,
    TweetListResponse,
    StatsResponse,
    ClassificationStats,
    SentimentStats,
    PreFilterStats
)


def get_tweets(
    session: Session,
    classification: Optional[str] = None,
    username: Optional[str] = None,
    sentiment: Optional[str] = None,
    ticker: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 10,
    offset: int = 0
) -> TweetListResponse:
    """
    Get tweets with filtering and pagination.

    Args:
        session: Database session
        classification: Filter by classification
        username: Filter by username
        sentiment: Filter by sentiment
        ticker: Filter by ticker symbol
        min_confidence: Minimum confidence score
        limit: Number of results
        offset: Number of results to skip

    Returns:
        TweetListResponse with tweets and pagination info
    """
    # Build query
    query = session.query(Tweet)

    # Apply filters
    if classification:
        query = query.filter(Tweet.classification == classification.upper())

    if username:
        query = query.filter(Tweet.username.ilike(f"%{username}%"))

    if sentiment:
        query = query.filter(Tweet.sentiment == sentiment.lower())

    if ticker:
        # PostgreSQL array contains operator
        query = query.filter(Tweet.tickers.contains([ticker.upper()]))

    if min_confidence is not None:
        query = query.filter(Tweet.confidence >= min_confidence)

    # Get total count before pagination
    total = query.count()

    # Apply ordering (most recent first)
    query = query.order_by(desc(Tweet.published_at))

    # Apply pagination
    tweets = query.limit(limit).offset(offset).all()

    # Convert to response models
    tweet_responses = [TweetResponse.model_validate(tweet) for tweet in tweets]

    return TweetListResponse(
        tweets=tweet_responses,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total
    )


def get_tweet_by_id(session: Session, tweet_id: int) -> Optional[TweetResponse]:
    """
    Get a single tweet by ID.

    Args:
        session: Database session
        tweet_id: Tweet ID

    Returns:
        TweetResponse or None if not found
    """
    tweet = session.query(Tweet).filter(Tweet.id == tweet_id).first()

    if tweet:
        return TweetResponse.model_validate(tweet)

    return None


def get_stats(session: Session) -> StatsResponse:
    """
    Get overall statistics.

    Args:
        session: Database session

    Returns:
        StatsResponse with statistics
    """
    # Total tweets
    total_tweets = session.query(func.count(Tweet.id)).scalar() or 0

    # Processed vs unprocessed
    processed_tweets = session.query(func.count(Tweet.id)).filter(Tweet.processed == True).scalar() or 0
    unprocessed_tweets = total_tweets - processed_tweets

    # Classification breakdown
    classification_counts = session.query(
        Tweet.classification,
        func.count(Tweet.id)
    ).filter(
        Tweet.classification.isnot(None)
    ).group_by(
        Tweet.classification
    ).all()

    classification_breakdown = ClassificationStats()
    for classification, count in classification_counts:
        if hasattr(classification_breakdown, classification):
            setattr(classification_breakdown, classification, count)

    # Sentiment breakdown
    sentiment_counts = session.query(
        Tweet.sentiment,
        func.count(Tweet.id)
    ).filter(
        Tweet.sentiment.isnot(None)
    ).group_by(
        Tweet.sentiment
    ).all()

    sentiment_breakdown = SentimentStats()
    for sentiment, count in sentiment_counts:
        if hasattr(sentiment_breakdown, sentiment):
            setattr(sentiment_breakdown, sentiment, count)

    # Pre-filter stats
    pre_filter_counts = session.query(
        Tweet.pre_filter_action,
        func.count(Tweet.id)
    ).filter(
        Tweet.pre_filter_action.isnot(None)
    ).group_by(
        Tweet.pre_filter_action
    ).all()

    pre_filter_stats = PreFilterStats(total=total_tweets)
    for action, count in pre_filter_counts:
        if action == 'skip':
            pre_filter_stats.skipped = count
        elif action == 'accept':
            pre_filter_stats.accepted = count
        elif action == 'triage':
            pre_filter_stats.triaged = count

    # Calculate skip rate
    if total_tweets > 0:
        pre_filter_stats.skip_rate = round(pre_filter_stats.skipped / total_tweets, 3)

    # Top tickers
    top_tickers = get_top_tickers(session, limit=10)

    # Top users
    top_users = get_top_users(session, limit=10)

    return StatsResponse(
        total_tweets=total_tweets,
        processed_tweets=processed_tweets,
        unprocessed_tweets=unprocessed_tweets,
        classification_breakdown=classification_breakdown,
        sentiment_breakdown=sentiment_breakdown,
        pre_filter_stats=pre_filter_stats,
        top_tickers=top_tickers,
        top_users=top_users
    )


def get_top_tickers(session: Session, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get top mentioned ticker symbols.

    Args:
        session: Database session
        limit: Number of results

    Returns:
        List of {ticker, count} dictionaries
    """
    # This is a bit complex in SQLAlchemy - we need to unnest the array
    # For SQLite (testing), we'll skip this
    # For PostgreSQL, we can use unnest
    try:
        # PostgreSQL-specific query
        from sqlalchemy import text

        query = text("""
            SELECT unnest(tickers) as ticker, COUNT(*) as count
            FROM tweets
            WHERE tickers IS NOT NULL AND array_length(tickers, 1) > 0
            GROUP BY ticker
            ORDER BY count DESC
            LIMIT :limit
        """)

        result = session.execute(query, {'limit': limit})
        return [{'ticker': row[0], 'count': row[1]} for row in result]

    except Exception:
        # Fallback for SQLite or if query fails
        return []


def get_top_users(session: Session, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get users with most tweets.

    Args:
        session: Database session
        limit: Number of results

    Returns:
        List of {username, count} dictionaries
    """
    result = session.query(
        Tweet.username,
        func.count(Tweet.id).label('count')
    ).filter(
        Tweet.username.isnot(None)
    ).group_by(
        Tweet.username
    ).order_by(
        desc('count')
    ).limit(limit).all()

    return [{'username': row[0], 'count': row[1]} for row in result]
