"""
Tests for Yellowbrick cookie-based authenticator.

Tests for the Yellowbrick cookie-based authenticator.
"""

import json
import tempfile
from pathlib import Path

import pytest


class TestYellowbrickAuthInit:
    """Test cases for YellowbrickAuth initialization."""

    def test_init_with_valid_path(self, tmp_path):
        """Should initialize with valid cookie file path."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("[]")

        auth = YellowbrickAuth(cookie_file)

        assert auth.cookie_file == cookie_file

    def test_init_with_path_object(self, tmp_path):
        """Should accept Path object."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("[]")

        auth = YellowbrickAuth(Path(cookie_file))

        assert isinstance(auth.cookie_file, Path)

    def test_init_with_string_path(self, tmp_path):
        """Should accept string path and convert to Path."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("[]")

        auth = YellowbrickAuth(str(cookie_file))

        assert isinstance(auth.cookie_file, Path)


class TestValidateCookies:
    """Test cases for cookie validation."""

    def test_validate_returns_true_for_valid_file(self, tmp_path):
        """Should return True when cookie file exists and is valid JSON."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookies = [
            {
                "name": "session_token",
                "value": "abc123",
                "domain": ".joinyellowbrick.com",
                "path": "/",
            }
        ]
        cookie_file.write_text(json.dumps(cookies))

        auth = YellowbrickAuth(cookie_file)

        assert auth.validate_cookies() is True

    def test_validate_returns_false_for_nonexistent_file(self, tmp_path):
        """Should return False when cookie file does not exist."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "nonexistent.json"

        auth = YellowbrickAuth(cookie_file)

        assert auth.validate_cookies() is False

    def test_validate_returns_false_for_invalid_json(self, tmp_path):
        """Should return False when file contains invalid JSON."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("not valid json {{{")

        auth = YellowbrickAuth(cookie_file)

        assert auth.validate_cookies() is False

    def test_validate_returns_false_for_non_list_json(self, tmp_path):
        """Should return False when JSON is not a list."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text('{"not": "a list"}')

        auth = YellowbrickAuth(cookie_file)

        assert auth.validate_cookies() is False

    def test_validate_returns_true_for_empty_list(self, tmp_path):
        """Should return True for empty cookie list (valid but empty)."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("[]")

        auth = YellowbrickAuth(cookie_file)

        assert auth.validate_cookies() is True


class TestLoadCookies:
    """Test cases for loading cookies from file."""

    def test_load_returns_cookie_list(self, tmp_path):
        """Should return list of cookie dictionaries."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookies = [
            {
                "name": "session_token",
                "value": "abc123",
                "domain": ".joinyellowbrick.com",
                "path": "/",
            },
            {
                "name": "user_id",
                "value": "12345",
                "domain": ".joinyellowbrick.com",
                "path": "/",
            },
        ]
        cookie_file.write_text(json.dumps(cookies))

        auth = YellowbrickAuth(cookie_file)
        result = auth.load_cookies()

        assert len(result) == 2
        assert result[0]["name"] == "session_token"
        assert result[0]["value"] == "abc123"
        assert result[1]["name"] == "user_id"

    def test_load_returns_empty_list_for_empty_file(self, tmp_path):
        """Should return empty list for empty cookie file."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("[]")

        auth = YellowbrickAuth(cookie_file)
        result = auth.load_cookies()

        assert result == []

    def test_load_raises_error_for_missing_file(self, tmp_path):
        """Should raise FileNotFoundError for missing file."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "nonexistent.json"

        auth = YellowbrickAuth(cookie_file)

        with pytest.raises(FileNotFoundError):
            auth.load_cookies()

    def test_load_raises_error_for_invalid_json(self, tmp_path):
        """Should raise JSONDecodeError for invalid JSON."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("invalid json")

        auth = YellowbrickAuth(cookie_file)

        with pytest.raises(json.JSONDecodeError):
            auth.load_cookies()

    def test_load_preserves_all_cookie_fields(self, tmp_path):
        """Should preserve all cookie fields from file."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookies = [
            {
                "name": "session_token",
                "value": "abc123xyz",
                "domain": ".joinyellowbrick.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
                "expires": 1735689600,
            }
        ]
        cookie_file.write_text(json.dumps(cookies))

        auth = YellowbrickAuth(cookie_file)
        result = auth.load_cookies()

        assert result[0]["name"] == "session_token"
        assert result[0]["value"] == "abc123xyz"
        assert result[0]["domain"] == ".joinyellowbrick.com"
        assert result[0]["path"] == "/"
        assert result[0]["httpOnly"] is True
        assert result[0]["secure"] is True
        assert result[0]["sameSite"] == "Lax"
        assert result[0]["expires"] == 1735689600


class TestInjectCookies:
    """Test cases for injecting cookies into Playwright context."""

    def test_inject_calls_add_cookies_on_context(self, tmp_path, mocker):
        """Should call add_cookies on the Playwright context."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookies = [
            {
                "name": "session_token",
                "value": "abc123",
                "domain": ".joinyellowbrick.com",
                "path": "/",
            }
        ]
        cookie_file.write_text(json.dumps(cookies))

        # Mock Playwright context
        mock_context = mocker.MagicMock()

        auth = YellowbrickAuth(cookie_file)
        auth.inject_cookies(mock_context)

        mock_context.add_cookies.assert_called_once()
        call_args = mock_context.add_cookies.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["name"] == "session_token"

    def test_inject_multiple_cookies(self, tmp_path, mocker):
        """Should inject multiple cookies."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookies = [
            {"name": "cookie1", "value": "value1", "domain": ".example.com", "path": "/"},
            {"name": "cookie2", "value": "value2", "domain": ".example.com", "path": "/"},
            {"name": "cookie3", "value": "value3", "domain": ".example.com", "path": "/"},
        ]
        cookie_file.write_text(json.dumps(cookies))

        mock_context = mocker.MagicMock()

        auth = YellowbrickAuth(cookie_file)
        auth.inject_cookies(mock_context)

        call_args = mock_context.add_cookies.call_args[0][0]
        assert len(call_args) == 3

    def test_inject_handles_empty_cookies(self, tmp_path, mocker):
        """Should handle empty cookie list gracefully."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("[]")

        mock_context = mocker.MagicMock()

        auth = YellowbrickAuth(cookie_file)
        auth.inject_cookies(mock_context)

        mock_context.add_cookies.assert_called_once_with([])

    def test_inject_raises_for_missing_file(self, tmp_path, mocker):
        """Should raise error if cookie file missing during inject."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "nonexistent.json"
        mock_context = mocker.MagicMock()

        auth = YellowbrickAuth(cookie_file)

        with pytest.raises(FileNotFoundError):
            auth.inject_cookies(mock_context)


class TestCookieFileFormat:
    """Test cases for different cookie file formats from browser exports."""

    def test_handles_chrome_export_format(self, tmp_path):
        """Should handle Chrome extension export format."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        # Chrome export format typically includes expirationDate
        cookies = [
            {
                "name": "session",
                "value": "token123",
                "domain": ".joinyellowbrick.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "expirationDate": 1735689600.123,  # Chrome uses float
            }
        ]
        cookie_file.write_text(json.dumps(cookies))

        auth = YellowbrickAuth(cookie_file)
        result = auth.load_cookies()

        assert len(result) == 1
        assert result[0]["name"] == "session"

    def test_handles_firefox_export_format(self, tmp_path):
        """Should handle Firefox export format."""
        from yellowbrick.authenticator import YellowbrickAuth

        cookie_file = tmp_path / "cookies.json"
        # Firefox export might use slightly different field names
        cookies = [
            {
                "name": "auth_token",
                "value": "xyz789",
                "domain": ".joinyellowbrick.com",
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "None",
            }
        ]
        cookie_file.write_text(json.dumps(cookies))

        auth = YellowbrickAuth(cookie_file)
        result = auth.load_cookies()

        assert len(result) == 1
        assert result[0]["sameSite"] == "None"
