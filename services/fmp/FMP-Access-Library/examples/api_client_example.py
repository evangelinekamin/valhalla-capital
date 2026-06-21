"""Example of using the FMP Data Client REST API."""

import asyncio
import requests
from typing import Dict, Any

# API Configuration
API_URL = "http://localhost:8000"
API_KEY = "demo-api-key-12345"  # Demo key included with server

class FMPAPIClient:
    """Simple client for FMP Data Client REST API."""

    def __init__(self, api_url: str, api_key: str):
        """Initialize API client.

        Args:
            api_url: Base URL of API server
            api_key: Your API key
        """
        self.api_url = api_url.rstrip("/")
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }

    def _handle_response(self, response: requests.Response) -> Dict[Any, Any]:
        """Handle API response.

        Args:
            response: Response object

        Returns:
            JSON response data

        Raises:
            Exception: If request failed
        """
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            raise Exception(f"Rate limit exceeded: {response.json()}")
        else:
            raise Exception(f"API error ({response.status_code}): {response.json()}")

    def health(self) -> Dict[str, Any]:
        """Check API health.

        Returns:
            Health status
        """
        response = requests.get(f"{self.api_url}/health")
        return self._handle_response(response)

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get real-time quote.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Quote data
        """
        response = requests.get(
            f"{self.api_url}/quote/{symbol}",
            headers=self.headers,
        )
        return self._handle_response(response)

    def get_profile(self, symbol: str) -> Dict[str, Any]:
        """Get company profile.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Profile data
        """
        response = requests.get(
            f"{self.api_url}/profile/{symbol}",
            headers=self.headers,
        )
        return self._handle_response(response)

    def get_ticker_data(self, data_request: Dict[str, Any]) -> Dict[str, Any]:
        """Get comprehensive ticker data.

        Args:
            data_request: DataRequest specification

        Returns:
            Comprehensive ticker data
        """
        response = requests.post(
            f"{self.api_url}/ticker",
            json=data_request,
            headers=self.headers,
        )
        return self._handle_response(response)

    def get_cache_status(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Cache status
        """
        response = requests.get(
            f"{self.api_url}/cache/status",
            headers=self.headers,
        )
        return self._handle_response(response)

    def clear_cache(self) -> Dict[str, Any]:
        """Clear all cached data.

        Returns:
            Success response
        """
        response = requests.post(
            f"{self.api_url}/cache/clear",
            headers=self.headers,
        )
        return self._handle_response(response)


def main():
    """Example usage of the API client."""
    # Initialize client
    client = FMPAPIClient(API_URL, API_KEY)

    print("FMP Data Client REST API - Example Usage\n")
    print("=" * 60)

    # 1. Check health
    print("\n1. Checking API health...")
    try:
        health = client.health()
        print(f"   Status: {health['status']}")
        print(f"   Version: {health['version']}")
        print(f"   Components: {health['components']}")
    except Exception as e:
        print(f"   Error: {e}")
        print("\n   Note: Make sure the server is running with: python run_server.py")
        return

    # 2. Get a quote
    print("\n2. Fetching quote for AAPL...")
    try:
        quote = client.get_quote("AAPL")
        print(f"   Symbol: {quote['symbol']}")
        print(f"   Price: ${quote['price']}")
        print(f"   Change: {quote['change']} ({quote['change_percent']}%)")
        print(f"   Volume: {quote['volume']:,}")
    except Exception as e:
        print(f"   Error: {e}")

    # 3. Get company profile
    print("\n3. Fetching profile for MSFT...")
    try:
        profile = client.get_profile("MSFT")
        print(f"   Name: {profile['name']}")
        print(f"   Sector: {profile.get('sector', 'N/A')}")
        print(f"   Industry: {profile.get('industry', 'N/A')}")
        print(f"   CEO: {profile.get('ceo', 'N/A')}")
        print(f"   Employees: {profile.get('employees', 'N/A'):,}")
    except Exception as e:
        print(f"   Error: {e}")

    # 4. Get comprehensive ticker data
    print("\n4. Fetching comprehensive data for GOOGL...")
    try:
        data_request = {
            "symbol": "GOOGL",
            "include_quote": True,
            "include_profile": True,
            "include_fundamentals": True,
            "fundamentals_periods": 4,
        }
        ticker_data = client.get_ticker_data(data_request)
        print(f"   Symbol: {ticker_data['symbol']}")
        print(f"   Cached: {ticker_data['cached']}")
        print(f"   Has quote: {'quote' in ticker_data['data']}")
        print(f"   Has profile: {'profile' in ticker_data['data']}")
        print(f"   Income statements: {len(ticker_data['data'].get('income_statements', []))}")
    except Exception as e:
        print(f"   Error: {e}")

    # 5. Check cache status
    print("\n5. Checking cache status...")
    try:
        cache = client.get_cache_status()
        print(f"   Enabled: {cache['enabled']}")
        if cache['enabled']:
            print(f"   Total entries: {cache.get('total_entries', 'N/A')}")
            print(f"   Hit rate: {cache.get('hit_rate', 'N/A')}")
    except Exception as e:
        print(f"   Error: {e}")

    print("\n" + "=" * 60)
    print("\nFor interactive API documentation, visit:")
    print(f"  {API_URL}/docs")
    print("\nFor more examples, see REST_API.md")


if __name__ == "__main__":
    main()
