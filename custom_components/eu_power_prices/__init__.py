"""The EU Power Prices integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EuPowerPricesApiClient
from .const import (
    CONF_AREA,
    CONF_SCAN_INTERVAL_SECONDS,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
)
from .coordinator import EuPowerPricesCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

type EuPowerPricesConfigEntry = ConfigEntry[EuPowerPricesCoordinator]


def _resolve_update_interval_seconds(entry: EuPowerPricesConfigEntry) -> int:
    """Resolve polling interval in seconds with legacy minutes fallback."""
    if CONF_SCAN_INTERVAL_SECONDS in entry.options:
        return int(entry.options[CONF_SCAN_INTERVAL_SECONDS])

    if CONF_SCAN_INTERVAL_MINUTES in entry.options:
        return int(entry.options[CONF_SCAN_INTERVAL_MINUTES]) * 60

    return DEFAULT_SCAN_INTERVAL_SECONDS


async def async_setup_entry(hass: HomeAssistant, entry: EuPowerPricesConfigEntry) -> bool:
    """Set up an EU Power Prices config entry (one per market area)."""
    session = async_get_clientsession(hass)
    client = EuPowerPricesApiClient(
        session=session,
        api_key=entry.data[CONF_API_KEY],
        area=entry.data[CONF_AREA],
    )

    update_interval_seconds = _resolve_update_interval_seconds(entry)

    coordinator = EuPowerPricesCoordinator(
        hass=hass,
        config_entry=entry,
        client=client,
        update_interval_seconds=update_interval_seconds,
    )
    await coordinator.async_load_forecast_history()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: EuPowerPricesConfigEntry
) -> None:
    """Reload the entry when options (e.g. polling interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EuPowerPricesConfigEntry) -> bool:
    """Unload an EU Power Prices config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
