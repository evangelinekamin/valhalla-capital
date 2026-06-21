"""News article models."""

from datetime import datetime
from typing import List, Optional

from pydantic import Field

from .base import FMPBaseModel


class NewsArticle(FMPBaseModel):
    """News article related to a stock."""

    # Article info
    title: str = Field(..., description="Article title")
    text: Optional[str] = Field(None, description="Article text/summary")
    url: str = Field(..., description="Article URL")

    # Publication info
    published_date: datetime = Field(
        ...,
        alias="publishedDate",
        description="Publication date"
    )
    site: str = Field(..., description="News site/source")

    # Stock association
    symbol: str = Field(..., description="Stock ticker symbol")

    # Image
    image: Optional[str] = Field(None, description="Article image URL")

    @property
    def preview(self) -> str:
        """Get article preview text.

        Returns:
            First 200 characters of text or title if text unavailable
        """
        if self.text:
            return self.text[:200] + ("..." if len(self.text) > 200 else "")
        return self.title

    def text_preview(self, max_length: int = 200) -> str:
        """Get article text preview with custom length.

        Args:
            max_length: Maximum number of characters in preview

        Returns:
            Truncated text with ellipsis or title if text unavailable
        """
        if self.text:
            return self.text[:max_length] + ("..." if len(self.text) > max_length else "")
        return self.title
