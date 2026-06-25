"""Constants for the EU Power Prices integration."""

from __future__ import annotations

DOMAIN = "eu_power_prices"

CONF_AREA = "area"
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"

DEFAULT_SCAN_INTERVAL_MINUTES = 60
MIN_SCAN_INTERVAL_MINUTES = 15
MAX_SCAN_INTERVAL_MINUTES = 180

API_BASE_URL = "https://api.eupowerprices.com"
API_FORECAST_PATH = "/v1/forecasts/{area}/latest"
HEADER_API_KEY = "X-API-Key"
TIMEOUT_SECONDS = 15

# Hours of forward-looking data exposed via the `forecast` attribute on the
# current-price sensor. The API returns ~16 days; we trim it for state size.
FORECAST_ATTR_HOURS = 48

# Known ENTSO-E style bidding-zone codes offered in the config flow dropdown.
# Not exhaustive (see requirements doc §4.1 - no confirmed /v1/areas endpoint
# to enumerate these from the API itself). The selector also accepts a
# custom typed value, so an unlisted code still works.
KNOWN_AREAS: list[str] = [
    "NL",
    "DE",
    "BE",
    "FR",
    "AT",
    "DK1",
    "DK2",
    "NO1",
    "NO2",
    "NO3",
    "NO4",
    "NO5",
    "SE1",
    "SE2",
    "SE3",
    "SE4",
    "FI",
    "ES",
    "PT",
    "IT",
    "PL",
    "CH",
    "GB",
    "IE",
    "LU",
]
