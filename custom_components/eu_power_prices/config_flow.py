"""Config flow for EU Power Prices."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    EuPowerPricesApiClient,
    EuPowerPricesAreaError,
    EuPowerPricesAuthError,
    EuPowerPricesConnectionError,
)
from .const import (
    CONF_AREA,
    CONF_SCAN_INTERVAL_SECONDS,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    KNOWN_AREAS,
    MAX_SCAN_INTERVAL_SECONDS,
    MIN_SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

_API_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

_AREA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AREA): SelectSelector(
            SelectSelectorConfig(
                options=KNOWN_AREAS,
                mode=SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        ),
    }
)


async def _async_try_validate(hass, api_key: str, area: str) -> str | None:
    """Call the API once; return an error code, or None on success."""
    session = async_get_clientsession(hass)
    client = EuPowerPricesApiClient(session=session, api_key=api_key, area=area)

    try:
        await client.async_get_latest_forecast()
    except EuPowerPricesAuthError:
        return "invalid_auth"
    except EuPowerPricesAreaError:
        return "invalid_area"
    except EuPowerPricesConnectionError:
        return "cannot_connect"
    return None


class EuPowerPricesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for EU Power Prices."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state shared across steps."""
        self._api_key: str | None = None
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: collect the API key (requirements §5.1)."""
        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY]
            return await self.async_step_area()

        return self.async_show_form(step_id="user", data_schema=_API_KEY_SCHEMA)

    async def async_step_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: collect and validate the market area."""
        errors: dict[str, str] = {}

        if user_input is not None:
            area = user_input[CONF_AREA].strip().upper()
            error = await _async_try_validate(self.hass, self._api_key, area)

            if error is None:
                await self.async_set_unique_id(area)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=area,
                    data={CONF_API_KEY: self._api_key, CONF_AREA: area},
                )

            errors["base"] = error

        return self.async_show_form(
            step_id="area", data_schema=_AREA_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Entry point when the coordinator raises ConfigEntryAuthFailed."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask only for a new API key; the area is kept as-is."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            area = self._reauth_entry.data[CONF_AREA]
            error = await _async_try_validate(self.hass, api_key, area)

            if error is None:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={**self._reauth_entry.data, CONF_API_KEY: api_key},
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=_API_KEY_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow for this entry."""
        return EuPowerPricesOptionsFlow()


class EuPowerPricesOptionsFlow(OptionsFlow):
    """Options flow: only the polling interval is user-adjustable (§5.2)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show/handle the single options field."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_SCAN_INTERVAL_SECONDS)
        if current is None:
            legacy_minutes = self.config_entry.options.get(CONF_SCAN_INTERVAL_MINUTES)
            if legacy_minutes is not None:
                current = int(legacy_minutes) * 60
            else:
                current = DEFAULT_SCAN_INTERVAL_SECONDS

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_SECONDS, default=current
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_SECONDS,
                        max=MAX_SCAN_INTERVAL_SECONDS,
                        step=5,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
