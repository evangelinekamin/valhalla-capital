"""
Pytest configuration and shared fixtures for Yellowbrick tests.
"""

import json
from pathlib import Path
from typing import Any

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_pitch_json() -> dict[str, Any]:
    """Load complete sample pitch JSON."""
    with open(FIXTURES_DIR / "sample_pitch.json") as f:
        return json.load(f)


@pytest.fixture
def sample_pitch_minimal_json() -> dict[str, Any]:
    """Load minimal sample pitch JSON (missing optional fields)."""
    with open(FIXTURES_DIR / "sample_pitch_minimal.json") as f:
        return json.load(f)


@pytest.fixture
def sample_pitch_bearish_json() -> dict[str, Any]:
    """Load bearish sample pitch JSON."""
    with open(FIXTURES_DIR / "sample_pitch_bearish.json") as f:
        return json.load(f)


@pytest.fixture
def sample_pitches_list_json() -> list[dict[str, Any]]:
    """Load list of sample pitches JSON."""
    with open(FIXTURES_DIR / "sample_pitches_list.json") as f:
        return json.load(f)
