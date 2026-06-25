"""Tests for custom_components.eu_power_prices.config_flow.

The API client itself is mocked here (it's already covered directly by
test_api.py) so these focus purely on flow wiring: steps, error surfacing,
uniqueness, reauth, and options.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.data_entry_flow import FlowResultType

from custom_components.eu_power_prices.api import (
    EuPowerPricesAreaError,
    EuPowerPricesAuthError,
    EuPowerPricesConnectionError,
)
from custom_components.eu_power_prices.const import CONF_AREA, CONF_SCAN_INTERVAL_MINUTES, DOMAIN

_VALIDATE_TARGET = (
    "custom_components.eu_power_prices.api.EuPowerPricesApiClient"
    ".async_get_latest_forecast"
)


@pytest.fixture
def mock_config_entry():
    """A pre-built config entry for options/reauth tests."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="NL",
        data={CONF_API_KEY: "old-key", CONF_AREA: "NL"},
        options={},
    )


async def test_user_flow_success(hass):
    """API key + area both validate -> a config entry is created."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "valid-key"}
    )
    assert result["step_id"] == "area"

    with patch(_VALIDATE_TARGET, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_AREA: "NL"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "NL"
    assert result["data"] == {CONF_API_KEY: "valid-key", CONF_AREA: "NL"}


async def test_user_flow_invalid_auth(hass):
    """A rejected API key surfaces invalid_auth and lets the user retry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "bad-key"}
    )

    with patch(_VALIDATE_TARGET, side_effect=EuPowerPricesAuthError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_AREA: "NL"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "area"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_invalid_area(hass):
    """A rejected area surfaces invalid_area."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "valid-key"}
    )

    with patch(_VALIDATE_TARGET, side_effect=EuPowerPricesAreaError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_AREA: "ZZ"}
        )

    assert result["errors"] == {"base": "invalid_area"}


async def test_user_flow_cannot_connect(hass):
    """A transient connection failure surfaces cannot_connect."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "valid-key"}
    )

    with patch(_VALIDATE_TARGET, side_effect=EuPowerPricesConnectionError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_AREA: "NL"}
        )

    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_area_aborts(hass):
    """Adding the same area twice aborts as already_configured."""
    with patch(_VALIDATE_TARGET, return_value=None):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "valid-key"}
        )
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_AREA: "NL"}
        )

        # Second attempt for the same area.
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "valid-key-2"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_AREA: "NL"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_updates_interval(hass, mock_config_entry):
    """The options flow accepts and stores a new polling interval."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL_MINUTES: 30}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_SCAN_INTERVAL_MINUTES: 30}


async def test_reauth_flow_success(hass, mock_config_entry):
    """A successful reauth updates the stored API key and keeps the area."""
    mock_config_entry.add_to_hass(hass)

    # Low-level trigger matching how Home Assistant itself starts a reauth
    # flow when the coordinator raises ConfigEntryAuthFailed.
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )
    assert result["step_id"] == "reauth_confirm"

    with patch(_VALIDATE_TARGET, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "new-key"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_API_KEY] == "new-key"
    assert mock_config_entry.data[CONF_AREA] == "NL"
