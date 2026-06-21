"""Data models for FMP API responses and requests."""

from .analyst import AnalystEstimate, AnalystGrade, PriceTarget, PriceTargetSummary
from .base import FMPBaseModel
from .events import DividendRecord, EarningsEvent, StockSplit
from .filings import FilingSummary, SECFiling
from .fundamentals import (
    BalanceSheet,
    CashFlowStatement,
    FinancialRatios,
    FinancialScores,
    IncomeStatement,
    KeyMetrics,
)
from .news import NewsArticle
from .ownership import HolderClassification, InsiderTrade, InstitutionalHolder
from .profile import CompanyProfile, Executive
from .quote import AftermarketQuote, Quote
from .request import DataRequest
from .ticker_data import TickerData
from .transcripts import EarningsTranscript, TranscriptSummary
from .valuation import DCFValuation, EnterpriseValue

__all__ = [
    # Base
    "FMPBaseModel",
    # Request
    "DataRequest",
    # Quote
    "Quote",
    "AftermarketQuote",
    # Profile
    "CompanyProfile",
    "Executive",
    # Events
    "DividendRecord",
    "StockSplit",
    "EarningsEvent",
    # Fundamentals
    "IncomeStatement",
    "BalanceSheet",
    "CashFlowStatement",
    "KeyMetrics",
    "FinancialRatios",
    "FinancialScores",
    # Valuation
    "DCFValuation",
    "EnterpriseValue",
    # Analyst
    "AnalystEstimate",
    "PriceTarget",
    "PriceTargetSummary",
    "AnalystGrade",
    # Ownership
    "InstitutionalHolder",
    "InsiderTrade",
    "HolderClassification",
    # Transcripts
    "EarningsTranscript",
    "TranscriptSummary",
    # Filings
    "SECFiling",
    "FilingSummary",
    # News
    "NewsArticle",
    # Main response model
    "TickerData",
]
