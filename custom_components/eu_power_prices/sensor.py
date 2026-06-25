"""Sensor platform for EU Power Prices."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
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
    """Set up all sensors for this area."""
    coordinator: EuPowerPricesCoordinator = entry.runtime_data
    async_add_entities([
        EuPowerPricesCurrentPriceSensor(coordinator),
        EuPowerPricesTodayMinSensor(coordinator),
        EuPowerPricesTodayMaxSensor(coordinator),
        EuPowerPricesNextCheapestHourSensor(coordinator),
        EuPowerPricesCheapestForecastHourSensor(coordinator),
    ])


def _current_hour_utc() -> datetime:
    """Return now, truncated to the top of the hour, in UTC."""
    return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)


def _today_points(data: EuPowerPricesData) -> list[PricePoint]:
    """Return all series points whose local date matches today in the area timezone."""
    tz = ZoneInfo(data.timezone)
    today = datetime.now(tz).date()
    return [p for p in data.series if p.ts_local.date() == today]


class _EuPowerPricesBaseSensor(
    CoordinatorEntity[EuPowerPricesCoordinator], SensorEntity
):
    """Shared base: device info, unique_id, and availability logic."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EuPowerPricesCoordinator) -> None:
        super().__init__(coordinator)
        area = coordinator.client.area
        self._attr_unique_id = f"{DOMAIN}_{area}_{self._attr_translation_key}"
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


class EuPowerPricesCurrentPriceSensor(_EuPowerPricesBaseSensor):
    """Price for the current local hour, with a forward-looking forecast attribute."""

    _attr_translation_key = "current_price"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Use the unit reported by the API (EUR/MWh in practice)."""
        data: EuPowerPricesData | None = self.coordinator.data
        return data.unit if data else None

    @property
    def native_value(self) -> float | None:
        """Return the next forecasted price at or after the current hour."""
        point = self._current_point()
        return point.price_eur_mwh if point else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the latest forecast plus a bounded snapshot history."""
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
            "forecast_history": self.coordinator.forecast_history,
            "generated_at": data.generated_at.isoformat(),
            "currency": data.currency,
            "area": data.area,
        }

    def _current_point(self) -> PricePoint | None:
        """Find the first forecast point at or after the current UTC hour."""
        data: EuPowerPricesData | None = self.coordinator.data
        if data is None:
            return None

        now_hour = _current_hour_utc()
        for point in data.series:
            if point.ts_utc >= now_hour:
                return point
        return None


class EuPowerPricesTodayMinSensor(_EuPowerPricesBaseSensor):
    """Lowest price today in the area's local timezone."""

    _attr_translation_key = "today_min_price"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    @property
    def native_unit_of_measurement(self) -> str | None:
        data: EuPowerPricesData | None = self.coordinator.data
        return data.unit if data else None

    @property
    def native_value(self) -> float | None:
        data: EuPowerPricesData | None = self.coordinator.data
        if data is None:
            return None
        points = _today_points(data)
        return min(p.price_eur_mwh for p in points) if points else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data: EuPowerPricesData | None = self.coordinator.data
        if data is None:
            return {}
        points = _today_points(data)
        if not points:
            return {}
        cheapest = min(points, key=lambda p: p.price_eur_mwh)
        return {"at": cheapest.ts_local.isoformat()}


class EuPowerPricesTodayMaxSensor(_EuPowerPricesBaseSensor):
    """Highest price today in the area's local timezone."""

    _attr_translation_key = "today_max_price"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    @property
    def native_unit_of_measurement(self) -> str | None:
        data: EuPowerPricesData | None = self.coordinator.data
        return data.unit if data else None

    @property
    def native_value(self) -> float | None:
        data: EuPowerPricesData | None = self.coordinator.data
        if data is None:
            return None
        points = _today_points(data)
        return max(p.price_eur_mwh for p in points) if points else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data: EuPowerPricesData | None = self.coordinator.data
        if data is None:
            return {}
        points = _today_points(data)
        if not points:
            return {}
        peak = max(points, key=lambda p: p.price_eur_mwh)
        return {"at": peak.ts_local.isoformat()}


class EuPowerPricesNextCheapestHourSensor(_EuPowerPricesBaseSensor):
    """Start time of the cheapest hour within the next 24 hours."""

    _attr_translation_key = "next_cheapest_hour"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        point = self._cheapest_in_next_24h()
        return point.ts_local if point else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data: EuPowerPricesData | None = self.coordinator.data
        point = self._cheapest_in_next_24h()
        if not point or not data:
            return {}
        return {"price": point.price_eur_mwh, "unit": data.unit}

    def _cheapest_in_next_24h(self) -> PricePoint | None:
        data: EuPowerPricesData | None = self.coordinator.data
        if data is None:
            return None
        now_hour = _current_hour_utc()
        cutoff = now_hour + timedelta(hours=24)
        window = [p for p in data.series if now_hour <= p.ts_utc < cutoff]
        return min(window, key=lambda p: p.price_eur_mwh) if window else None


class EuPowerPricesCheapestForecastHourSensor(_EuPowerPricesBaseSensor):
    """Start time of the cheapest hour across the full remaining forecast horizon."""

    _attr_translation_key = "cheapest_forecast_hour"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        point = self._cheapest_remaining()
        return point.ts_local if point else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data: EuPowerPricesData | None = self.coordinator.data
        point = self._cheapest_remaining()
        if not point or not data:
            return {}
        return {"price": point.price_eur_mwh, "unit": data.unit}

    def _cheapest_remaining(self) -> PricePoint | None:
        data: EuPowerPricesData | None = self.coordinator.data
        if data is None:
            return None
        now_hour = _current_hour_utc()
        remaining = [p for p in data.series if p.ts_utc >= now_hour]
        return min(remaining, key=lambda p: p.price_eur_mwh) if remaining else None
