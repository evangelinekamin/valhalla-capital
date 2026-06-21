"""SEC filing summarization using Claude."""

import logging
from typing import Optional

from fmp_data_client.config import FMPConfig
from fmp_data_client.summarizer.base import BaseSummarizer
from fmp_data_client.models.filings import SECFiling

logger = logging.getLogger(__name__)


FILING_SYSTEM_PROMPT = """You are a securities analyst specializing in SEC filing analysis.
Your task is to extract and summarize the most material information from SEC filings.

Focus on:
1. Material business changes or events
2. Financial condition and results
3. Risk factors (new or changed)
4. Management's discussion and analysis (MD&A)
5. Legal proceedings or regulatory matters
6. Material contracts or agreements

Be concise, objective, and highlight only information that would materially impact investment decisions.
Use plain language and avoid excessive regulatory jargon."""


class FilingSummarizer(BaseSummarizer):
    """
    Summarizer for SEC filings using Claude.

    Provides intelligent summarization of SEC filings (10-K, 10-Q, 8-K, etc.) with:
    - Executive summary
    - Material changes
    - Risk factors
    - Financial highlights
    - Management commentary

    Example:
        ```python
        config = FMPConfig.from_env()
        summarizer = FilingSummarizer(config)

        # Summarize a filing
        summary = await summarizer.summarize_filing(filing_text, "10-K")
        print(summary.executive_summary)
        ```
    """

    def __init__(
        self,
        config: FMPConfig,
        model: Optional[str] = None,
    ) -> None:
        """
        Initialize filing summarizer.

        Args:
            config: FMP configuration with Anthropic API key
            model: Claude model to use (defaults to Haiku for cost efficiency)
        """
        # Use Haiku by default for cost efficiency on long documents
        if model is None:
            model = "claude-3-haiku-20240307"

        super().__init__(config, model)

    async def summarize_filing(
        self,
        filing: SECFiling,
        filing_text: str,
        focus_areas: Optional[list[str]] = None,
    ) -> dict:
        """
        Summarize an SEC filing.

        Args:
            filing: SECFiling object with metadata
            filing_text: Full text content of the filing
            focus_areas: Optional list of specific areas to focus on

        Returns:
            Dictionary with:
                - executive_summary: Brief overview (3-4 sentences)
                - material_changes: List of material business changes
                - risk_factors: New or changed risk factors
                - financial_highlights: Key financial information
                - management_commentary: Notable MD&A points
                - legal_matters: Legal proceedings or regulatory issues
                - key_takeaways: Bullet list of most important points

        Raises:
            ValueError: If filing text is empty
        """
        if not filing_text or len(filing_text.strip()) < 100:
            raise ValueError("Filing text is empty or too short")

        logger.info(
            f"Summarizing {filing.filing_type} filing for {filing.symbol} "
            f"from {filing.filing_date}"
        )

        # Build the prompt
        prompt = self._build_filing_prompt(filing, filing_text, focus_areas)

        # Call Claude (use higher token limit for comprehensive filings)
        max_tokens = 2048 if filing.filing_type in ["10-K", "10-Q"] else 1024

        response = await self._call_claude(
            prompt=prompt,
            system_prompt=FILING_SYSTEM_PROMPT,
            max_tokens=max_tokens,
        )

        # Parse the structured response
        summary = self._parse_filing_response(response, filing)

        logger.info(f"Successfully summarized {filing.filing_type} for {filing.symbol}")

        return summary

    def _build_filing_prompt(
        self,
        filing: SECFiling,
        filing_text: str,
        focus_areas: Optional[list[str]],
    ) -> str:
        """Build the prompt for filing summarization."""
        # Determine filing type context
        filing_context = self._get_filing_context(filing.filing_type)

        focus_instruction = ""
        if focus_areas:
            focus_instruction = f"\n\nPay special attention to: {', '.join(focus_areas)}"

        # Truncate filing text if too long (keep first 20k chars)
        # Claude can handle more, but we want to be cost-effective
        truncated_text = filing_text[:20000]
        if len(filing_text) > 20000:
            truncated_text += "\n\n[... document truncated for analysis ...]"

        prompt = f"""Analyze the following SEC {filing.filing_type} filing for {filing.symbol} filed on {filing.filing_date}.

{filing_context}{focus_instruction}

Provide a structured summary with the following sections:

1. **Executive Summary**: 3-4 sentence overview of the most material information
2. **Material Changes**: Bullet list of significant business changes or events
3. **Risk Factors**: New or materially changed risk factors (if any)
4. **Financial Highlights**: Key financial metrics or changes (if discussed)
5. **Management Commentary**: Notable points from MD&A section
6. **Legal Matters**: Legal proceedings or regulatory issues (if any)
7. **Key Takeaways**: Top 3-5 most important points for investors

Format your response in clear sections with headers.

---

FILING DOCUMENT:

{truncated_text}

---

Provide your analysis:"""

        return prompt

    def _get_filing_context(self, filing_type: str) -> str:
        """Get context-specific instructions based on filing type."""
        contexts = {
            "10-K": "This is an annual report. Focus on full-year performance, strategic direction, and comprehensive risk factors.",
            "10-Q": "This is a quarterly report. Focus on quarterly performance, material changes since last filing, and updated risks.",
            "8-K": "This is a current report of material events. Focus on the specific event(s) being reported and their impact.",
            "DEF 14A": "This is a proxy statement. Focus on governance matters, executive compensation, and shareholder proposals.",
            "S-1": "This is an IPO registration. Focus on business model, use of proceeds, and key risk factors.",
        }

        return contexts.get(
            filing_type,
            "Focus on material information that would impact investment decisions.",
        )

    def _parse_filing_response(
        self,
        response: str,
        filing: SECFiling,
    ) -> dict:
        """Parse Claude's response into structured format."""
        # Initialize result
        result = {
            "symbol": filing.symbol,
            "filing_type": filing.filing_type,
            "filing_date": filing.filing_date,
            "accepted_date": filing.accepted_date,
            "full_summary": response,
            "executive_summary": "",
            "material_changes": [],
            "risk_factors": [],
            "financial_highlights": [],
            "management_commentary": "",
            "legal_matters": [],
            "key_takeaways": [],
        }

        # Try to extract structured sections
        lines = response.split("\n")
        current_section = None
        section_content = []

        for line in lines:
            line_lower = line.lower().strip()

            # Detect section headers
            if "executive summary" in line_lower or "overview" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "executive_summary"
                section_content = []
            elif "material changes" in line_lower or "significant changes" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "material_changes"
                section_content = []
            elif "risk factors" in line_lower or "risks" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "risk_factors"
                section_content = []
            elif "financial highlights" in line_lower or "financial" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "financial_highlights"
                section_content = []
            elif "management commentary" in line_lower or "md&a" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "management_commentary"
                section_content = []
            elif "legal matters" in line_lower or "legal proceedings" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "legal_matters"
                section_content = []
            elif "key takeaways" in line_lower or "takeaways" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "key_takeaways"
                section_content = []
            elif line.strip() and current_section:
                # Add content to current section
                section_content.append(line.strip())

        # Save last section
        if current_section and section_content:
            self._save_section(result, current_section, section_content)

        return result

    def _save_section(
        self,
        result: dict,
        section: str,
        content: list[str],
    ) -> None:
        """Save parsed section content to result dictionary."""
        text = "\n".join(content).strip()

        if section == "executive_summary":
            result["executive_summary"] = text
        elif section in ["material_changes", "risk_factors", "financial_highlights", "legal_matters", "key_takeaways"]:
            # Extract bullet points
            items = [
                line.strip("- •*").strip()
                for line in content
                if line.strip() and (len(line.strip()) < 3 or line.strip()[0] in "-•*")
            ]
            result[section] = items
        elif section == "management_commentary":
            result["management_commentary"] = text

    async def summarize_filing_by_type(
        self,
        symbol: str,
        filing_type: str,
        filing_text: str,
        filing_date: Optional[str] = None,
    ) -> dict:
        """
        Summarize a filing from raw text and metadata.

        Convenience method for when you have filing text but not the full object.

        Args:
            symbol: Stock symbol
            filing_type: Type of filing (10-K, 10-Q, 8-K, etc.)
            filing_text: Full filing text content
            filing_date: Optional filing date string

        Returns:
            Summary dictionary (same format as summarize_filing)
        """
        from datetime import datetime

        # Create temporary filing object
        filing = SECFiling(
            symbol=symbol,
            filing_date=filing_date or datetime.now().strftime("%Y-%m-%d"),
            accepted_date=datetime.now(),
            filing_type=filing_type,
            link="",  # Not needed for summarization
        )

        return await self.summarize_filing(filing, filing_text)

    async def quick_summary(
        self,
        filing_text: str,
        filing_type: str = "10-K",
        max_length: int = 500,
    ) -> str:
        """
        Generate a quick, brief summary of a filing.

        Useful for rapid screening of multiple filings.

        Args:
            filing_text: Filing text content
            filing_type: Type of filing
            max_length: Maximum characters in summary

        Returns:
            Brief summary string
        """
        prompt = f"""Provide a brief {max_length}-character summary of this {filing_type} filing.
Focus only on the single most material piece of information for investors.

FILING TEXT:
{filing_text[:5000]}

Brief summary:"""

        response = await self._call_claude(
            prompt=prompt,
            max_tokens=256,
        )

        return response.strip()
