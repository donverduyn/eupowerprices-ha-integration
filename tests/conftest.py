"""Shared fixtures for the EU Power Prices test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/ visible to Home Assistant during tests.

    Provided by pytest-homeassistant-custom-component; required for any
    custom integration test, hence autouse here.
    """
    return enable_custom_integrations


@pytest.fixture
def sample_forecast_payload() -> dict:
    """Return the trimmed sample API payload as a dict."""
    return json.loads((FIXTURES_DIR / "sample_forecast.json").read_text())
