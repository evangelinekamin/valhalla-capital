"""Earnings transcript summarization using Claude."""

import logging
from typing import Optional

from fmp_data_client.config import FMPConfig
from fmp_data_client.summarizer.base import BaseSummarizer
from fmp_data_client.models.transcripts import EarningsTranscript

logger = logging.getLogger(__name__)


TRANSCRIPT_SYSTEM_PROMPT = """You are a financial analyst specializing in earnings call analysis.
Your task is to summarize earnings call transcripts in a clear, structured, and actionable format.

Focus on:
1. Key financial metrics and performance highlights
2. Forward-looking guidance and outlook
3. Strategic initiatives and business updates
4. Management commentary on trends and challenges
5. Notable Q&A insights

Be concise, objective, and highlight only material information that would be relevant to investors."""


class TranscriptSummarizer(BaseSummarizer):
    """
    Summarizer for earnings call transcripts using Claude.

    Provides intelligent summarization of earnings transcripts with:
    - Executive summary
    - Key metrics and highlights
    - Forward guidance
    - Sentiment analysis
    - Strategic themes

    Example:
        ```python
        config = FMPConfig.from_env()
        summarizer = TranscriptSummarizer(config)

        # Summarize a transcript
        summary = await summarizer.summarize_transcript(transcript)
        print(summary.executive_summary)
        ```
    """

    def __init__(
        self,
        config: FMPConfig,
        model: Optional[str] = None,
    ) -> None:
        """
        Initialize transcript summarizer.

        Args:
            config: FMP configuration with Anthropic API key
            model: Claude model to use (defaults to Haiku for cost efficiency)
        """
        # Use Haiku by default for cost efficiency
        if model is None:
            model = "claude-3-haiku-20240307"

        super().__init__(config, model)

    async def summarize_transcript(
        self,
        transcript: EarningsTranscript,
        include_sentiment: bool = True,
    ) -> dict:
        """
        Summarize an earnings call transcript.

        Args:
            transcript: EarningsTranscript object with content
            include_sentiment: Whether to include sentiment analysis

        Returns:
            Dictionary with:
                - executive_summary: Brief overview (2-3 sentences)
                - key_metrics: List of important financial metrics mentioned
                - forward_guidance: Management's outlook and guidance
                - strategic_themes: Key strategic initiatives
                - sentiment: Overall sentiment (if requested)
                - qa_highlights: Notable Q&A insights

        Raises:
            ValueError: If transcript content is empty
        """
        if not transcript.content:
            raise ValueError("Transcript content is empty")

        logger.info(
            f"Summarizing transcript for {transcript.symbol} "
            f"Q{transcript.quarter} {transcript.year}"
        )

        # Build the prompt
        prompt = self._build_transcript_prompt(transcript, include_sentiment)

        # Call Claude
        response = await self._call_claude(
            prompt=prompt,
            system_prompt=TRANSCRIPT_SYSTEM_PROMPT,
            max_tokens=1500,  # Sufficient for detailed summary
        )

        # Parse the structured response
        summary = self._parse_transcript_response(response, transcript)

        logger.info(f"Successfully summarized transcript for {transcript.symbol}")

        return summary

    def _build_transcript_prompt(
        self,
        transcript: EarningsTranscript,
        include_sentiment: bool,
    ) -> str:
        """Build the prompt for transcript summarization."""
        sentiment_instruction = ""
        if include_sentiment:
            sentiment_instruction = """
5. **Sentiment**: Overall tone (bullish/neutral/bearish) with brief justification
"""

        prompt = f"""Analyze the following earnings call transcript for {transcript.symbol} Q{transcript.quarter} {transcript.year}.

Provide a structured summary with the following sections:

1. **Executive Summary**: 2-3 sentence overview of the quarter's performance and key takeaways
2. **Key Metrics**: Bullet list of important financial metrics and performance indicators mentioned
3. **Forward Guidance**: Management's outlook, guidance, and future expectations
4. **Strategic Themes**: Major strategic initiatives, business updates, or changes{sentiment_instruction}
6. **Q&A Highlights**: Notable insights or concerns raised during Q&A (if applicable)

Format your response in clear sections with headers.

---

TRANSCRIPT:

{transcript.content[:15000]}

---

Provide your analysis:"""

        return prompt

    def _parse_transcript_response(
        self,
        response: str,
        transcript: EarningsTranscript,
    ) -> dict:
        """Parse Claude's response into structured format."""
        # Initialize result
        result = {
            "symbol": transcript.symbol,
            "quarter": transcript.quarter,
            "year": transcript.year,
            "date": transcript.call_date,
            "full_summary": response,
            "executive_summary": "",
            "key_metrics": [],
            "forward_guidance": "",
            "strategic_themes": [],
            "sentiment": None,
            "qa_highlights": [],
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
            elif "key metrics" in line_lower or "performance indicators" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "key_metrics"
                section_content = []
            elif "forward guidance" in line_lower or "outlook" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "forward_guidance"
                section_content = []
            elif "strategic themes" in line_lower or "strategic initiatives" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "strategic_themes"
                section_content = []
            elif "sentiment" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "sentiment"
                section_content = []
            elif "q&a" in line_lower or "q and a" in line_lower:
                if current_section and section_content:
                    self._save_section(result, current_section, section_content)
                current_section = "qa_highlights"
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
        elif section == "key_metrics":
            # Extract bullet points
            metrics = [
                line.strip("- •*").strip()
                for line in content
                if line.strip() and line.strip()[0] in "-•*"
            ]
            result["key_metrics"] = metrics
        elif section == "forward_guidance":
            result["forward_guidance"] = text
        elif section == "strategic_themes":
            themes = [
                line.strip("- •*").strip()
                for line in content
                if line.strip() and line.strip()[0] in "-•*"
            ]
            result["strategic_themes"] = themes
        elif section == "sentiment":
            result["sentiment"] = text
        elif section == "qa_highlights":
            highlights = [
                line.strip("- •*").strip()
                for line in content
                if line.strip() and line.strip()[0] in "-•*"
            ]
            result["qa_highlights"] = highlights

    async def summarize_transcript_text(
        self,
        symbol: str,
        quarter: int,
        year: int,
        content: str,
    ) -> dict:
        """
        Summarize a transcript from raw text.

        Convenience method for when you have transcript text but not the full object.

        Args:
            symbol: Stock symbol
            quarter: Quarter number (1-4)
            year: Year
            content: Transcript text content

        Returns:
            Summary dictionary (same format as summarize_transcript)
        """
        # Create temporary transcript object
        from datetime import datetime

        transcript = EarningsTranscript(
            symbol=symbol,
            quarter=quarter,
            year=year,
            date=datetime.now(),
            content=content,
        )

        return await self.summarize_transcript(transcript)
