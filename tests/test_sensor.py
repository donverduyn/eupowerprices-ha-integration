"""Tests for custom_components.eu_power_prices.sensor.

These set up a full config entry (with the API client mocked) and assert on
the resulting entity state, looked up via the entity registry rather than a
hardcoded entity_id, so the test doesn't depend on exact slugify behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from homeassistant.const import CONF_API_KEY
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eu_power_prices.api import (
    EuPowerPricesConnectionError,
    EuPowerPricesData,
    PricePoint,
)
from custom_components.eu_power_prices.const import CONF_AREA, DOMAIN

_VALIDATE_TARGET = (
    "custom_components.eu_power_prices.api.EuPowerPricesApiClient"
    ".async_get_latest_forecast"
)


def _build_sample_data() -> EuPowerPricesData:
    """Build a tiny series anchored on the current hour, so no time-mocking
    library is needed: the "current hour" entry is always real "now"."""
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


async def test_current_price_sensor_state(hass):
    """The sensor's state matches the series entry for the current hour."""
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

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_NL_current_price"
    )
    assert entity_id is not None

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "42.5"
    assert state.attributes["unit_of_measurement"] == "EUR/MWh"
    assert state.attributes["currency"] == "EUR"
    assert state.attributes["area"] == "NL"
    assert len(state.attributes["forecast"]) == 2


async def test_sensor_survives_a_single_transient_failure(hass):
    """One transient API failure keeps the last good state, not unavailable."""
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

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_NL_current_price"
    )

    coordinator = entry.runtime_data
    with patch(_VALIDATE_TARGET, side_effect=EuPowerPricesConnectionError("boom")):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "42.5"
    assert state.state != "unavailable"


async def test_sensor_goes_unavailable_after_sustained_failures(hass):
    """Enough *consecutive* failures do eventually flip the entity, and a
    subsequent success brings it straight back."""
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

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_NL_current_price"
    )
    coordinator = entry.runtime_data

    with patch(_VALIDATE_TARGET, side_effect=EuPowerPricesConnectionError("boom")):
        for _ in range(coordinator.MAX_CONSECUTIVE_FAILURES):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "unavailable"

    with patch(_VALIDATE_TARGET, return_value=data):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "42.5"
