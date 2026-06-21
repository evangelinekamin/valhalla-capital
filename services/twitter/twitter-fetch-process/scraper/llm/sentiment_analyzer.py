from typing import Dict, Any


# Keyword sets for fallback sentiment analysis
BULLISH_KEYWORDS = {
    'bullish', 'bull', 'buy', 'long', 'calls', 'upgrade', 'beat', 'beating',
    'outperform', 'positive', 'growth', 'rally', 'surge', 'soar', 'jump',
    'gain', 'rise', 'increase', 'breakthrough', 'innovation', 'record',
    'strong', 'success', 'excellent', 'revenue growth', 'profit', 'earnings beat',
    'moon', 'rocket', 'green', 'up', 'higher', 'momentum',
    'breaking out', 'breakout', 'upside', 'buy the dip', 'dip',
    'accumulating', 'going up',
}

BEARISH_KEYWORDS = {
    'bearish', 'bear', 'sell', 'short', 'puts', 'downgrade', 'miss', 'missing',
    'underperform', 'negative', 'decline', 'crash', 'plunge', 'dive', 'drop',
    'fall', 'decrease', 'problem', 'issue', 'concern', 'warning', 'risk',
    'weak', 'failure', 'poor', 'revenue decline', 'loss', 'earnings miss',
    'red', 'down', 'lower', 'selling pressure', 'recall', 'investigation',
    'breaking down', 'breakdown', 'downside', 'distributing', 'going down',
    'sell signal', 'weak momentum',
}


class SentimentAnalyzer:
    """Analyze sentiment of financial tweets."""

    VALID_SENTIMENTS = {'bullish', 'bearish', 'neutral'}

    def __init__(self):
        """Initialize sentiment analyzer."""
        self.bullish_keywords = BULLISH_KEYWORDS
        self.bearish_keywords = BEARISH_KEYWORDS

    def extract_from_llm_response(self, response: Dict[str, Any]) -> str:
        """
        Extract sentiment from LLM JSON response.

        Args:
            response: LLM response dictionary

        Returns:
            Sentiment: 'bullish', 'bearish', or 'neutral'
        """
        if not response:
            return 'neutral'

        sentiment = response.get('sentiment', '').lower().strip()

        # Validate sentiment
        if sentiment in self.VALID_SENTIMENTS:
            return sentiment

        # If invalid sentiment, return neutral
        return 'neutral'

    def analyze_with_keywords(self, text: str) -> str:
        """
        Analyze sentiment using keyword matching as fallback.

        Args:
            text: Tweet content

        Returns:
            Sentiment: 'bullish', 'bearish', or 'neutral'
        """
        if not text:
            return 'neutral'

        text_lower = text.lower()

        # Count bullish and bearish keywords
        bullish_count = sum(1 for keyword in self.bullish_keywords if keyword in text_lower)
        bearish_count = sum(1 for keyword in self.bearish_keywords if keyword in text_lower)

        # Determine sentiment based on keyword counts
        if bullish_count == 0 and bearish_count == 0:
            return 'neutral'
        elif bullish_count == bearish_count:
            return 'neutral'
        elif bullish_count > bearish_count:
            return 'bullish'
        else:
            return 'bearish'

    def analyze(
        self,
        text: str,
        llm_response: Dict[str, Any] = None
    ) -> str:
        """
        Analyze sentiment using LLM response with keyword fallback.

        Args:
            text: Tweet content
            llm_response: Optional LLM response with sentiment

        Returns:
            Sentiment: 'bullish', 'bearish', or 'neutral'
        """
        # Try LLM sentiment first
        if llm_response:
            sentiment = self.extract_from_llm_response(llm_response)
            if sentiment in self.VALID_SENTIMENTS:
                return sentiment

        # Fallback to keyword analysis
        return self.analyze_with_keywords(text)

    def normalize_sentiment(self, sentiment: str) -> str:
        """
        Normalize sentiment to valid values.

        Args:
            sentiment: Raw sentiment value

        Returns:
            Normalized sentiment: 'bullish', 'bearish', or 'neutral'
        """
        if not sentiment:
            return 'neutral'

        sentiment = sentiment.lower().strip()

        # Handle common variations
        if sentiment in {'positive', 'optimistic', 'confident', 'buy'}:
            return 'bullish'
        elif sentiment in {'negative', 'pessimistic', 'concerned', 'sell'}:
            return 'bearish'
        elif sentiment in self.VALID_SENTIMENTS:
            return sentiment
        else:
            return 'neutral'
