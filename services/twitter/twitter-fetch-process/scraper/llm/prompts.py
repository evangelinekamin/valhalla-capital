import json
from pathlib import Path
from typing import Dict, Any, Optional


def load_triage_config() -> Dict[str, Any]:
    """Load triage configuration from config file."""
    config_path = Path(__file__).parent.parent / 'config' / 'triage_config.json'
    with open(config_path, 'r') as f:
        return json.load(f)


def build_system_prompt() -> str:
    """Build system prompt for tweet classification with ticker and sentiment extraction."""
    config = load_triage_config()
    classifications = config['classifications']

    prompt = """You are a financial market intelligence analyst. Your task is to classify tweets for a trading system and extract key information.

For each tweet, provide:
1. CLASSIFICATION: Categorize the tweet's market relevance
2. CONFIDENCE: Your confidence level (0.0 to 1.0)
3. TICKERS: Extract all stock ticker symbols mentioned
4. SENTIMENT: Determine the market sentiment
5. REASONING: Brief explanation of your classification

CLASSIFICATION CATEGORIES:

"""

    for classification, details in classifications.items():
        prompt += f"\n{classification}:\n"
        prompt += f"  Description: {details['description']}\n"
        prompt += f"  Examples:\n"
        for example in details['examples']:
            prompt += f"    - {example}\n"

    prompt += """
SENTIMENT CATEGORIES:
- bullish: Positive outlook, expecting price increase or positive developments
- bearish: Negative outlook, expecting price decrease or negative developments
- neutral: Balanced or informational without clear directional bias

TICKER EXTRACTION:
- Extract ONLY actual stock/ETF ticker symbols (e.g., AAPL, TSLA, MSFT)
- Include tickers with or without $ prefix
- Validate tickers are 1-5 capital letters
- Maximum 10 tickers per tweet
- If no tickers mentioned, return empty array
- Do NOT include these as tickers:
  - Common words: AI, US, UK, IT, OR, AN, TO, IN, OF, VS, ONLY, JUST, SEES
  - Financial terms: EBIT, EPS, PE, EV, ROI, ROE, NAV, MBO, LBO, IPO, ETF
  - Organizations/agencies: SEC, FED, FDA, DOJ, RFK, NATO, OPEC, IMF, HHS
- When in doubt whether a word is a ticker or common term, omit it

RESPONSE FORMAT (JSON):
{
  "classification": "CRITICAL|IMPORTANT|ROUTINE|SKIP",
  "confidence": 0.95,
  "tickers": ["AAPL", "MSFT"],
  "sentiment": "bullish|bearish|neutral",
  "reasoning": "Brief explanation"
}

FEW-SHOT EXAMPLES:

Example 1:
Tweet: "Apple CEO Tim Cook announces major breakthrough in chip technology. $AAPL"
Response:
{
  "classification": "IMPORTANT",
  "confidence": 0.9,
  "tickers": ["AAPL"],
  "sentiment": "bullish",
  "reasoning": "Product innovation announcement from CEO, significant but not immediately market-moving"
}

Example 2:
Tweet: "BREAKING: Tesla recalls 2 million vehicles due to safety defect. Stock down 8% premarket. $TSLA"
Response:
{
  "classification": "CRITICAL",
  "confidence": 0.98,
  "tickers": ["TSLA"],
  "sentiment": "bearish",
  "reasoning": "Major product recall with immediate market impact and price movement"
}

Example 3:
Tweet: "Interesting chart pattern on $SPY. Could see a breakout soon. #trading"
Response:
{
  "classification": "ROUTINE",
  "confidence": 0.7,
  "tickers": ["SPY"],
  "sentiment": "neutral",
  "reasoning": "General technical analysis commentary, not actionable information"
}

Example 4:
Tweet: "Good morning everyone! Hope you have a great day trading 🚀"
Response:
{
  "classification": "SKIP",
  "confidence": 0.95,
  "tickers": [],
  "sentiment": "neutral",
  "reasoning": "Generic greeting with no market information or ticker mentions"
}

Always respond with valid JSON matching the format above."""

    return prompt


def build_user_prompt(username: str, content: str, author_context: Optional[str] = None) -> str:
    """Build user prompt for a specific tweet, optionally with author context."""
    prompt = f"Analyze this tweet:\n\n"
    prompt += f"Username: @{username}\n"
    if author_context:
        prompt += f"Author Context: {author_context}\n"
    prompt += f"Content: {content}\n\n"
    prompt += "Provide your analysis in JSON format."
    return prompt


def build_batch_prompt(tweets: list) -> str:
    """Build prompt for batch processing multiple tweets."""
    prompt = "Analyze these tweets and provide a JSON array of responses:\n\n"

    for i, tweet in enumerate(tweets, 1):
        prompt += f"Tweet {i}:\n"
        prompt += f"Username: @{tweet.get('username', 'unknown')}\n"
        author_context = tweet.get('author_context')
        if author_context:
            prompt += f"Author Context: {author_context}\n"
        prompt += f"Content: {tweet.get('content', '')}\n\n"

    prompt += "\nRespond with a JSON array containing one analysis object for each tweet, in the same order. Keep reasoning to one sentence."

    return prompt
