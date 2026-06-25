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
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
)
from .coordinator import EuPowerPricesCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

type EuPowerPricesConfigEntry = ConfigEntry[EuPowerPricesCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EuPowerPricesConfigEntry) -> bool:
    """Set up an EU Power Prices config entry (one per market area)."""
    session = async_get_clientsession(hass)
    client = EuPowerPricesApiClient(
        session=session,
        api_key=entry.data[CONF_API_KEY],
        area=entry.data[CONF_AREA],
    )

    update_interval_minutes = entry.options.get(
        CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
    )

    coordinator = EuPowerPricesCoordinator(
        hass=hass,
        config_entry=entry,
        client=client,
        update_interval_minutes=update_interval_minutes,
    )
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
