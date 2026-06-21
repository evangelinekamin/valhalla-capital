"""SEC filing models."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import Field

from .base import FMPBaseModel


class SECFiling(FMPBaseModel):
    """SEC filing document."""

    symbol: str = Field(..., description="Stock ticker symbol")
    cik: Optional[str] = Field(None, description="SEC CIK number")

    # Filing info
    filing_type: str = Field(
        ...,
        alias="type",
        description="Filing type (10-K, 10-Q, 8-K, etc.)"
    )
    filing_date: date = Field(
        ...,
        alias="filingDate",
        description="Filing date"
    )
    accepted_date: Optional[datetime] = Field(
        None,
        alias="acceptedDate",
        description="Date accepted by SEC"
    )

    # Period
    period_of_report: Optional[date] = Field(
        None,
        alias="periodOfReport",
        description="Period covered by report"
    )

    # Document identifiers
    accession_number: str = Field(
        ...,
        alias="accessionNumber",
        description="SEC accession number"
    )

    # Links
    link: str = Field(..., description="Link to filing on SEC EDGAR")
    final_link: Optional[str] = Field(
        None,
        alias="finalLink",
        description="Direct link to document"
    )

    # Content (if fetched)
    content: Optional[str] = Field(
        None,
        description="Filing content/text"
    )

    @property
    def is_annual_report(self) -> bool:
        """Check if this is an annual report.

        Returns:
            True if 10-K filing
        """
        return self.filing_type == "10-K"

    @property
    def is_quarterly_report(self) -> bool:
        """Check if this is a quarterly report.

        Returns:
            True if 10-Q filing
        """
        return self.filing_type == "10-Q"

    @property
    def is_current_report(self) -> bool:
        """Check if this is a current report.

        Returns:
            True if 8-K filing
        """
        return self.filing_type == "8-K"


class FilingSummary(FMPBaseModel):
    """AI-generated summary of SEC filing."""

    # Reference
    symbol: str = Field(..., description="Stock ticker symbol")
    filing_type: str = Field(..., description="Filing type")
    filing_date: date = Field(..., description="Filing date")
    accession_number: str = Field(..., description="SEC accession number")

    # Executive summary
    executive_summary: str = Field(
        ...,
        description="Brief executive summary of filing"
    )

    # Key sections (for 10-K/10-Q)
    business_overview: Optional[str] = Field(
        None,
        description="Business overview section summary"
    )
    risk_factors: Optional[List[str]] = Field(
        None,
        description="Key risk factors identified"
    )
    md_and_a_summary: Optional[str] = Field(
        None,
        description="Management Discussion & Analysis summary"
    )

    # Financial highlights
    financial_highlights: Optional[List[str]] = Field(
        None,
        description="Key financial highlights"
    )

    # Material events (for 8-K)
    material_events: Optional[List[str]] = Field(
        None,
        description="Material events disclosed (for 8-K filings)"
    )

    # Legal matters
    legal_proceedings: Optional[List[str]] = Field(
        None,
        description="Legal proceedings mentioned"
    )

    # Changes
    significant_changes: Optional[List[str]] = Field(
        None,
        description="Significant changes from previous filings"
    )

    # Red flags
    red_flags: Optional[List[str]] = Field(
        None,
        description="Potential red flags or concerns"
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
    def has_red_flags(self) -> bool:
        """Check if any red flags were identified.

        Returns:
            True if red flags present
        """
        return bool(self.red_flags and len(self.red_flags) > 0)
