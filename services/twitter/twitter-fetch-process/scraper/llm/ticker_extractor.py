import re
from typing import List, Dict, Any, Set


# Common words to exclude from ticker extraction
COMMON_WORDS = {
    'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HER',
    'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS', 'HIM', 'HIS', 'HOW',
    'MAN', 'NEW', 'NOW', 'OLD', 'SEE', 'TWO', 'WAY', 'WHO', 'BOY', 'DID',
    'ITS', 'LET', 'PUT', 'SAY', 'SHE', 'TOO', 'USE', 'MAY', 'OWN', 'SAW',
    'WHY', 'BIG', 'GOT', 'RUN', 'TOP', 'HOT', 'SET', 'TRY', 'FAR', 'FUN',
    'YES', 'YET', 'BAD', 'BIT', 'BUY', 'CUT', 'DUE', 'END', 'FEW', 'FIT',
    'GOD', 'JOB', 'LAW', 'LEG', 'LIE', 'LOT', 'LOW', 'MAP', 'MRS', 'NOR',
    'OFF', 'PAY', 'PER', 'RED', 'SIT', 'SON', 'TAX', 'TEN', 'VIA', 'WAR',
    'WIN', 'ADD', 'AGE', 'AGO', 'AID', 'AIM', 'AIR', 'ARM', 'ART', 'ASK',
    'BAG', 'BAR', 'BED', 'BET', 'BOX', 'BUS', 'CAR', 'CEO', 'CTO', 'CFO',
    # Trading terms that are not tickers
    'SELL', 'LONG', 'SHORT', 'CALL', 'HOLD', 'OPEN', 'HIGH', 'CLOSE',
    # Common abbreviations that are not tickers
    'IPO', 'ETF', 'GDP', 'USA', 'NYC', 'EST', 'PST', 'UTC',
    # Two-letter words (almost always false positives without $ prefix)
    'AI', 'AM', 'AN', 'AT', 'BY', 'DO', 'EM', 'EU', 'EV', 'GO', 'IF',
    'IN', 'IS', 'IT', 'ME', 'MY', 'NO', 'OF', 'ON', 'OR', 'PE', 'PM',
    'SO', 'TO', 'UK', 'UP', 'US', 'VS', 'WE',
    # Financial metrics / terms that are not tickers
    'EBIT', 'EPS', 'ROI', 'ROE', 'YTD', 'QOQ', 'MOM', 'YOY',
    'GAAP', 'NAV', 'AUM', 'MBO', 'LBO', 'DCF',
    # Common 3-5 letter words appearing uppercase in tweets
    'ALSO', 'ONLY', 'JUST', 'EVEN', 'VERY', 'MUCH', 'MANY', 'SOME',
    'LIKE', 'OVER', 'SUCH', 'MAKE', 'MOST', 'GOOD', 'KNOW', 'TAKE',
    'WILL', 'BEEN', 'HAVE', 'SAID', 'EACH', 'MADE', 'FIND', 'HERE',
    'THEY', 'THAN', 'WHEN', 'WHAT', 'WITH', 'THIS', 'THAT', 'FROM',
    'THEM', 'THEN', 'WERE', 'WANT', 'LAST', 'NEXT', 'NEED', 'WELL',
    'BACK', 'DOWN', 'SEES', 'STILL', 'EVERY', 'AFTER', 'ABOUT',
    # Government agencies / proper nouns commonly in financial tweets
    'RFK', 'SEC', 'FED', 'FDA', 'DOJ', 'EPA', 'IRS', 'HHS',
    'NATO', 'OPEC', 'IMF', 'NASA', 'FBI', 'CIA',
}


class TickerExtractor:
    """Extract stock ticker symbols from tweets."""

    def __init__(self, max_tickers: int = 10):
        """
        Initialize ticker extractor.

        Args:
            max_tickers: Maximum number of tickers to extract per tweet
        """
        self.max_tickers = max_tickers

        # Regex patterns for ticker extraction
        self.patterns = [
            r'\$([A-Z]{1,5})\b',  # $AAPL format
            r'\b([A-Z]{3,5})\b',  # AAPL format (3-5 chars; 2-char tickers need $ prefix)
        ]

    def extract_from_llm_response(self, response: Dict[str, Any]) -> List[str]:
        """
        Extract tickers from LLM JSON response.

        Args:
            response: LLM response dictionary

        Returns:
            List of ticker symbols (uppercase)
        """
        if not response:
            return []

        tickers = response.get('tickers', [])

        if not isinstance(tickers, list):
            return []

        # Validate and normalize tickers
        validated = []
        for ticker in tickers:
            if isinstance(ticker, str):
                ticker = ticker.upper().strip()
                # Validate format: 1-5 capital letters
                if re.match(r'^[A-Z]{1,5}$', ticker):
                    # Exclude common words
                    if ticker not in COMMON_WORDS:
                        validated.append(ticker)

        # Return unique tickers, limited to max_tickers
        return list(dict.fromkeys(validated))[:self.max_tickers]

    def extract_with_regex(self, text: str) -> List[str]:
        """
        Extract tickers using regex patterns as fallback.

        Args:
            text: Tweet content

        Returns:
            List of ticker symbols (uppercase)
        """
        if not text:
            return []

        tickers: Set[str] = set()

        for pattern in self.patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                ticker = match.upper().strip()
                # Validate format
                if re.match(r'^[A-Z]{1,5}$', ticker):
                    # Exclude common words
                    if ticker not in COMMON_WORDS:
                        tickers.add(ticker)

        # Return sorted list, limited to max_tickers
        return sorted(list(tickers))[:self.max_tickers]

    def combine_extractions(
        self,
        llm_tickers: List[str],
        regex_tickers: List[str]
    ) -> List[str]:
        """
        Combine tickers from LLM and regex extraction.

        LLM tickers are prioritized, regex fills in any missed.

        Args:
            llm_tickers: Tickers from LLM response
            regex_tickers: Tickers from regex extraction

        Returns:
            Combined list of unique tickers
        """
        # Start with LLM tickers (more reliable)
        combined = list(llm_tickers)

        # Add regex tickers that weren't caught by LLM
        for ticker in regex_tickers:
            if ticker not in combined and len(combined) < self.max_tickers:
                combined.append(ticker)

        return combined[:self.max_tickers]

    def extract(
        self,
        text: str,
        llm_response: Dict[str, Any] = None
    ) -> List[str]:
        """
        Extract tickers using both LLM and regex methods.

        Args:
            text: Tweet content
            llm_response: Optional LLM response with tickers

        Returns:
            List of unique ticker symbols
        """
        llm_tickers = []
        if llm_response:
            llm_tickers = self.extract_from_llm_response(llm_response)

        regex_tickers = self.extract_with_regex(text)

        return self.combine_extractions(llm_tickers, regex_tickers)

    def validate_ticker(self, ticker: str) -> bool:
        """
        Validate if a string is a valid ticker symbol.

        Args:
            ticker: Ticker symbol to validate

        Returns:
            True if valid, False otherwise
        """
        if not ticker:
            return False

        ticker = ticker.upper().strip()

        # Check format: 1-5 capital letters
        if not re.match(r'^[A-Z]{1,5}$', ticker):
            return False

        # Check not a common word
        if ticker in COMMON_WORDS:
            return False

        return True
