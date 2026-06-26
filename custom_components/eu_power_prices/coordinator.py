"""DataUpdateCoordinator for EU Power Prices."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    EuPowerPricesApiClient,
    EuPowerPricesAreaError,
    EuPowerPricesAuthError,
    EuPowerPricesConnectionError,
    EuPowerPricesData,
    PricePoint,
)
from .const import DOMAIN, FORECAST_HISTORY_MAX_SNAPSHOTS

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
    _STORE_VERSION = 1

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: EuPowerPricesApiClient,
        update_interval_seconds: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}_{client.area}",
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.client = client
        self.consecutive_failures = 0
        self.forecast_history: list[dict[str, object]] = []
        self._history_store = Store[dict[str, object]](
            hass,
            self._STORE_VERSION,
            f"{DOMAIN}_{config_entry.entry_id}_forecast_history",
        )

    async def async_load_forecast_history(self) -> None:
        """Restore forecast history from persistent storage."""
        stored = await self._history_store.async_load()
        if not isinstance(stored, dict):
            return

        history = stored.get("forecast_history")
        if not isinstance(history, list):
            return

        snapshots = [item for item in history if isinstance(item, dict)]
        self.forecast_history = snapshots[-FORECAST_HISTORY_MAX_SNAPSHOTS:]

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
            await self._append_forecast_history(data)
            return data

    async def _append_forecast_history(self, data: EuPowerPricesData) -> None:
        """Keep a bounded list of forecast snapshots for chart overlays."""
        snapshot = self._build_forecast_snapshot(data)
        if (
            self.forecast_history
            and self.forecast_history[-1].get("generated_at") == snapshot["generated_at"]
        ):
            self.forecast_history[-1] = snapshot
        else:
            self.forecast_history.append(snapshot)

        self.forecast_history = self.forecast_history[-FORECAST_HISTORY_MAX_SNAPSHOTS:]
        await self._history_store.async_save({"forecast_history": self.forecast_history})

    @staticmethod
    def _build_forecast_snapshot(data: EuPowerPricesData) -> dict[str, object]:
        """Convert one forecast payload into a serializable chart snapshot."""
        return {
            "generated_at": data.generated_at.isoformat(),
            "area": data.area,
            "timezone": data.timezone,
            "currency": data.currency,
            "series": [
                {
                    "ts_local": point.ts_local.isoformat(),
                    "ts_utc": point.ts_utc.isoformat(),
                    "price": point.price_eur_mwh,
                }
                for point in data.series
            ],
        }
