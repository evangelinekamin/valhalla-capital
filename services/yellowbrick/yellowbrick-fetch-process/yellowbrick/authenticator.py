"""
Cookie-based authenticator for Yellowbrick scraper.

Loads cookies exported from browser and injects them into Playwright context.
This approach avoids automated login by using manually exported session cookies.

IMPORTANT: This module follows immutability principles:
- Cookie data is loaded fresh each time (no internal caching that could mutate)
- All methods return new objects, never modify inputs
"""

import json
from pathlib import Path
from typing import Any


class YellowbrickAuth:
    """
    Cookie-based authentication for Yellowbrick.

    Loads session cookies from a JSON file (exported from browser extension)
    and injects them into a Playwright browser context.

    Usage:
        auth = YellowbrickAuth(Path("cookies.json"))
        if auth.validate_cookies():
            cookies = auth.load_cookies()
            auth.inject_cookies(playwright_context)
    """

    def __init__(self, cookie_file: str | Path) -> None:
        """
        Initialize authenticator with path to cookie file.

        Args:
            cookie_file: Path to JSON file containing exported cookies.
                         Can be string or Path object.
        """
        if isinstance(cookie_file, str):
            self.cookie_file = Path(cookie_file)
        else:
            self.cookie_file = cookie_file

    def validate_cookies(self) -> bool:
        """
        Validate that cookie file exists and contains valid JSON.

        Returns:
            True if file exists and contains valid JSON list, False otherwise.
        """
        # Check file exists
        if not self.cookie_file.exists():
            return False

        # Try to parse JSON
        try:
            with open(self.cookie_file, encoding="utf-8") as f:
                data = json.load(f)

            # Must be a list
            if not isinstance(data, list):
                return False

            return True

        except (json.JSONDecodeError, OSError):
            return False

    def load_cookies(self) -> list[dict[str, Any]]:
        """
        Load cookies from JSON file.

        Returns:
            List of cookie dictionaries, each containing at minimum:
            - name: Cookie name
            - value: Cookie value
            - domain: Cookie domain
            - path: Cookie path

            May also contain:
            - httpOnly: bool
            - secure: bool
            - sameSite: str
            - expires/expirationDate: int/float

        Raises:
            FileNotFoundError: If cookie file does not exist.
            json.JSONDecodeError: If file contains invalid JSON.
        """
        with open(self.cookie_file, encoding="utf-8") as f:
            cookies = json.load(f)

        # Return a new list (immutability)
        return list(cookies)

    def inject_cookies(self, context: Any) -> None:
        """
        Inject cookies into a Playwright browser context.

        Args:
            context: Playwright BrowserContext instance.
                     Must have add_cookies(cookies: list[dict]) method.

        Raises:
            FileNotFoundError: If cookie file does not exist.
            json.JSONDecodeError: If file contains invalid JSON.
        """
        cookies = self.load_cookies()

        # Normalize cookies for Playwright compatibility
        normalized_cookies = []
        for cookie in cookies:
            # Start with required fields only
            normalized = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie["domain"],
                "path": cookie.get("path", "/"),
            }

            # Add optional fields that Playwright supports
            if "httpOnly" in cookie:
                normalized["httpOnly"] = cookie["httpOnly"]
            if "secure" in cookie:
                normalized["secure"] = cookie["secure"]

            # Handle expiration (Playwright uses "expires" as Unix timestamp)
            if "expirationDate" in cookie:
                normalized["expires"] = cookie["expirationDate"]
            elif "expires" in cookie:
                normalized["expires"] = cookie["expires"]

            # Playwright requires sameSite to be one of: Strict, Lax, None (capitalized)
            # Browser exports may use lowercase or "unspecified"
            if "sameSite" in cookie:
                same_site = str(cookie["sameSite"]).lower()
                if same_site == "strict":
                    normalized["sameSite"] = "Strict"
                elif same_site == "lax":
                    normalized["sameSite"] = "Lax"
                elif same_site == "none":
                    normalized["sameSite"] = "None"
                # Skip unspecified or invalid values (Playwright will use default)

            normalized_cookies.append(normalized)

        context.add_cookies(normalized_cookies)
