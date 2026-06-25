"""Tests for custom_components.eu_power_prices.diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from homeassistant.const import CONF_API_KEY
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eu_power_prices.api import EuPowerPricesData, PricePoint
from custom_components.eu_power_prices.const import CONF_AREA, DOMAIN
from custom_components.eu_power_prices.diagnostics import (
    async_get_config_entry_diagnostics,
)

_VALIDATE_TARGET = (
    "custom_components.eu_power_prices.api.EuPowerPricesApiClient"
    ".async_get_latest_forecast"
)


def _build_sample_data() -> EuPowerPricesData:
    now_hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    return EuPowerPricesData(
        area="NL",
        timezone="Europe/Amsterdam",
        currency="EUR",
        unit="EUR/MWh",
        generated_at=now_hour,
        series=[
            PricePoint(ts_utc=now_hour, ts_local=now_hour, price_eur_mwh=42.5),
            PricePoint(
                ts_utc=now_hour + timedelta(hours=1),
                ts_local=now_hour + timedelta(hours=1),
                price_eur_mwh=50.0,
            ),
        ],
    )


async def test_diagnostics_redacts_api_key(hass):
    """The API key must be replaced with **REDACTED** in diagnostics output."""
    data = _build_sample_data()

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="NL",
        data={CONF_API_KEY: "super-secret", CONF_AREA: "NL"},
    )
    entry.add_to_hass(hass)

    with patch(_VALIDATE_TARGET, return_value=data):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry_data"][CONF_API_KEY] == "**REDACTED**"
    assert diag["entry_data"][CONF_AREA] == "NL"
    assert diag["last_update_success"] is True


async def test_diagnostics_forecast_summary(hass):
    """Diagnostics includes a forecast summary with area, timezone and series length."""
    data = _build_sample_data()

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="NL",
        data={CONF_API_KEY: "key", CONF_AREA: "NL"},
    )
    entry.add_to_hass(hass)

    with patch(_VALIDATE_TARGET, return_value=data):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)
    summary = diag["forecast_summary"]

    assert summary["area"] == "NL"
    assert summary["timezone"] == "Europe/Amsterdam"
    assert summary["series_length"] == 2
    assert summary["generated_at"] is not None
