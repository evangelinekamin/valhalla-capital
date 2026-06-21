"""Earnings transcript models."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import Field

from .base import FMPBaseModel


class EarningsTranscript(FMPBaseModel):
    """Earnings call transcript."""

    symbol: str = Field(..., description="Stock ticker symbol")
    quarter: int = Field(..., description="Fiscal quarter (1-4)")
    year: int = Field(..., description="Fiscal year")
    call_date: date = Field(..., alias="date", description="Earnings call date")

    # Content
    content: str = Field(..., description="Full transcript text")

    @property
    def period_label(self) -> str:
        """Get formatted period label.

        Returns:
            Period label (e.g., "Q1 2024")
        """
        return f"Q{self.quarter} {self.year}"

    @property
    def word_count(self) -> int:
        """Get approximate word count.

        Returns:
            Number of words in transcript
        """
        return len(self.content.split())


class TranscriptSummary(FMPBaseModel):
    """AI-generated summary of earnings transcript."""

    # Reference
    symbol: str = Field(..., description="Stock ticker symbol")
    quarter: int = Field(..., description="Fiscal quarter")
    year: int = Field(..., description="Fiscal year")
    call_date: date = Field(..., alias="date", description="Earnings call date")

    # Sentiment
    overall_sentiment: str = Field(
        ...,
        description="Overall sentiment (positive, neutral, negative)"
    )
    sentiment_score: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Sentiment score (-1.0 to 1.0)"
    )

    # Summary
    executive_summary: str = Field(
        ...,
        description="Brief executive summary (2-3 sentences)"
    )

    # Key points
    key_points: List[str] = Field(
        ...,
        description="List of key points discussed"
    )

    # Financial highlights
    revenue_guidance: Optional[str] = Field(
        None,
        description="Revenue guidance mentioned"
    )
    earnings_guidance: Optional[str] = Field(
        None,
        description="Earnings guidance mentioned"
    )
    guidance_summary: Optional[str] = Field(
        None,
        description="Overall guidance summary"
    )

    # Strategic points
    strategic_initiatives: Optional[List[str]] = Field(
        None,
        description="Strategic initiatives mentioned"
    )
    risks_mentioned: Optional[List[str]] = Field(
        None,
        description="Risks or challenges mentioned"
    )
    opportunities_mentioned: Optional[List[str]] = Field(
        None,
        description="Opportunities mentioned"
    )

    # Notable items
    notable_quotes: Optional[List[str]] = Field(
        None,
        description="Notable quotes from executives"
    )

    # Analyst Q&A
    analyst_concerns: Optional[List[str]] = Field(
        None,
        description="Key concerns raised by analysts"
    )

    # Metadata
    model_used: Optional[str] = Field(
        None,
        description="AI model used for summarization"
    )
    summary_generated_at: Optional[date] = Field(
        None,
        description="Date summary was generated"
    )

    @property
    def is_positive(self) -> bool:
        """Check if sentiment is positive.

        Returns:
            True if positive sentiment
        """
        return self.overall_sentiment.lower() == "positive"

    @property
    def is_negative(self) -> bool:
        """Check if sentiment is negative.

        Returns:
            True if negative sentiment
        """
        return self.overall_sentiment.lower() == "negative"
