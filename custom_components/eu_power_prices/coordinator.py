"""DataUpdateCoordinator for EU Power Prices."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    EuPowerPricesApiClient,
    EuPowerPricesAreaError,
    EuPowerPricesAuthError,
    EuPowerPricesConnectionError,
    EuPowerPricesData,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class EuPowerPricesCoordinator(DataUpdateCoordinator[EuPowerPricesData]):
    """Polls one area's forecast and hands parsed data to entities."""

    # Number of consecutive failed polls tolerated before entities are
    # marked unavailable. By default, Home Assistant's CoordinatorEntity
    # flips `available` to False on the very first failed poll; that's
    # tighter than the requirements doc's goal of riding out a single
    # transient blip (timeout, brief 5xx) without flapping the entity, so
    # this counter plus `is_available` below is what actually delivers
    # that behavior (requirements §3 / §6.3).
    MAX_CONSECUTIVE_FAILURES = 3

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: EuPowerPricesApiClient,
        update_interval_minutes: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}_{client.area}",
            update_interval=timedelta(minutes=update_interval_minutes),
        )
        self.client = client
        self.consecutive_failures = 0

    @property
    def is_available(self) -> bool:
        """True once we have data, as long as failures haven't piled up."""
        return (
            self.data is not None
            and self.consecutive_failures < self.MAX_CONSECUTIVE_FAILURES
        )

    async def _async_update_data(self) -> EuPowerPricesData:
        """Fetch the latest forecast.

        Auth failures trigger Home Assistant's reauth flow; everything else
        is treated as transient and retried on the normal poll interval
        rather than tearing the entry down (requirements §5.3 / §6.3).
        """
        try:
            data = await self.client.async_get_latest_forecast()
        except EuPowerPricesAuthError as err:
            self.consecutive_failures += 1
            raise ConfigEntryAuthFailed("API key was rejected") from err
        except (EuPowerPricesAreaError, EuPowerPricesConnectionError) as err:
            self.consecutive_failures += 1
            if self.data is not None and self.consecutive_failures < self.MAX_CONSECUTIVE_FAILURES:
                # Return cached data so HA keeps last_update_success=True and
                # the entity stays available during a transient blip. Only on
                # the Nth consecutive failure do we raise, which flips
                # last_update_success True→False and triggers listener
                # notification so the entity can write "unavailable".
                return self.data
            raise UpdateFailed(str(err)) from err
        else:
            self.consecutive_failures = 0
            return data
