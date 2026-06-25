"""Sensor platform for EU Power Prices."""

from __future__ import annotations

from datetime import UTC, datetime
import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import EuPowerPricesData, PricePoint
from .const import DOMAIN, FORECAST_ATTR_HOURS
from .coordinator import EuPowerPricesCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the single MVP sensor for this area (requirements §5.4)."""
    coordinator: EuPowerPricesCoordinator = entry.runtime_data
    async_add_entities([EuPowerPricesCurrentPriceSensor(coordinator)])


def _current_hour_utc() -> datetime:
    """Return now, truncated to the top of the hour, in UTC."""
    return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)


class EuPowerPricesCurrentPriceSensor(
    CoordinatorEntity[EuPowerPricesCoordinator], SensorEntity
):
    """Price for the current local hour, with a forward-looking forecast attribute."""

    _attr_has_entity_name = True
    _attr_translation_key = "current_price"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: EuPowerPricesCoordinator) -> None:
        """Set up identifiers that don't change between updates."""
        super().__init__(coordinator)
        area = coordinator.client.area
        self._attr_unique_id = f"{DOMAIN}_{area}_current_price"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, area)},
            name=f"EU Power Prices ({area})",
            manufacturer="eupowerprices.com",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Stay available through a transient blip (see coordinator)."""
        return self.coordinator.is_available

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Use the unit reported by the API (EUR/MWh in practice)."""
        data: EuPowerPricesData | None = self.coordinator.data
        return data.unit if data else None

    @property
    def native_value(self) -> float | None:
        """Return the price for the current hour, or None if not found."""
        point = self._current_point()
        return point.price_eur_mwh if point else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose a trimmed forward-looking forecast plus payload metadata."""
        data: EuPowerPricesData | None = self.coordinator.data
        if data is None:
            return {}

        now_hour = _current_hour_utc()
        forecast = [
            {"ts_local": point.ts_local.isoformat(), "price": point.price_eur_mwh}
            for point in data.series
            if point.ts_utc >= now_hour
        ][:FORECAST_ATTR_HOURS]

        return {
            "forecast": forecast,
            "generated_at": data.generated_at.isoformat(),
            "currency": data.currency,
            "area": data.area,
        }

    def _current_point(self) -> PricePoint | None:
        """Find the series entry matching the current UTC hour, if any."""
        data: EuPowerPricesData | None = self.coordinator.data
        if data is None:
            return None

        now_hour = _current_hour_utc()
        for point in data.series:
            if point.ts_utc == now_hour:
                return point
        return None
