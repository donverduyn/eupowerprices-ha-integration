"""Tests for custom_components.eu_power_prices.sensor.

These set up a full config entry (with the API client mocked) and assert on
the resulting entity state, looked up via the entity registry rather than a
hardcoded entity_id, so the test doesn't depend on exact slugify behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from homeassistant.const import CONF_API_KEY
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_UNKNOWN
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.eu_power_prices.api import (
    EuPowerPricesAuthError,
    EuPowerPricesConnectionError,
    EuPowerPricesData,
    PricePoint,
)
from custom_components.eu_power_prices.const import (
    CONF_AREA,
    CONF_SCAN_INTERVAL_SECONDS,
    DOMAIN,
)

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
    assert len(state.attributes["forecast_history"]) == 1
    assert state.attributes["forecast_history"][0]["generated_at"] == data.generated_at.isoformat()


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
    assert len(state.attributes["forecast_history"]) == 1


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


async def test_sensor_appends_forecast_history_on_each_successful_refresh(hass):
    """Each successful poll adds a new forecast snapshot for chart overlays."""
    first = _build_sample_data()
    second = EuPowerPricesData(
        area="NL",
        timezone="Europe/Amsterdam",
        currency="EUR",
        unit="EUR/MWh",
        generated_at=first.generated_at + timedelta(hours=1),
        series=[
            PricePoint(
                ts_utc=point.ts_utc,
                ts_local=point.ts_local,
                price_eur_mwh=point.price_eur_mwh + 1.0,
            )
            for point in first.series
        ],
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="NL",
        data={CONF_API_KEY: "key", CONF_AREA: "NL"},
    )
    entry.add_to_hass(hass)

    with patch(_VALIDATE_TARGET, return_value=first):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = entry.runtime_data
    with patch(_VALIDATE_TARGET, return_value=second):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    state = hass.states.get(
        er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_NL_current_price")
    )
    history = state.attributes["forecast_history"]

    assert len(history) == 2
    assert history[0]["generated_at"] == first.generated_at.isoformat()
    assert history[1]["generated_at"] == second.generated_at.isoformat()


async def test_sensor_state_uses_next_forecast_hour_when_no_exact_match(hass):
    """If there is no exact current-hour match, the sensor uses the next
    forecast point instead of becoming unknown."""
    now_hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    past = now_hour - timedelta(hours=2)
    future = now_hour + timedelta(hours=1)
    data = EuPowerPricesData(
        area="NL",
        timezone="Europe/Amsterdam",
        currency="EUR",
        unit="EUR/MWh",
        generated_at=past,
        series=[
            PricePoint(ts_utc=past, ts_local=past, price_eur_mwh=30.0),
            PricePoint(ts_utc=future, ts_local=future, price_eur_mwh=31.0),
        ],
    )

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

    state = hass.states.get(entity_id)
    assert state.state == "31.0"


async def test_coordinator_auth_failure_raises_config_entry_auth_failed(hass):
    """An EuPowerPricesAuthError from the API raises ConfigEntryAuthFailed
    so Home Assistant can start the reauth flow, and increments the counter."""
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

    coordinator = entry.runtime_data
    assert coordinator.consecutive_failures == 0

    with patch(_VALIDATE_TARGET, side_effect=EuPowerPricesAuthError("expired")):
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    assert coordinator.consecutive_failures == 1


async def test_options_listener_reloads_entry(hass):
    """Saving new options via the config entry fires _async_options_updated
    which reloads the entry and picks up the new poll interval."""
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

    original_coordinator = entry.runtime_data

    with patch(_VALIDATE_TARGET, return_value=data):
        hass.config_entries.async_update_entry(
            entry, options={CONF_SCAN_INTERVAL_SECONDS: 30}
        )
        await hass.async_block_till_done()

    new_coordinator = entry.runtime_data
    assert new_coordinator is not original_coordinator
    assert new_coordinator.update_interval.total_seconds() == 30
