"""Diagnostics support for EU Power Prices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .coordinator import EuPowerPricesCoordinator

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, with the API key redacted."""
    coordinator: EuPowerPricesCoordinator = entry.runtime_data
    data = coordinator.data

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "forecast_summary": {
            "area": data.area if data else None,
            "timezone": data.timezone if data else None,
            "generated_at": data.generated_at.isoformat() if data else None,
            "series_length": len(data.series) if data else 0,
        },
    }
