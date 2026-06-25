"""Minimal async client for the EU Power Prices API.

Kept deliberately separate from the coordinator so it can be unit tested
without spinning up Home Assistant, and so the error taxonomy used by the
config flow and the coordinator comes from one place (requirements §5.1/§5.3).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import aiohttp

from .const import API_BASE_URL, API_FORECAST_PATH, HEADER_API_KEY, TIMEOUT_SECONDS


class EuPowerPricesApiError(Exception):
    """Base error for the EU Power Prices API client."""


class EuPowerPricesAuthError(EuPowerPricesApiError):
    """The API key was rejected (HTTP 401/403)."""


class EuPowerPricesAreaError(EuPowerPricesApiError):
    """The area code was rejected (HTTP 404)."""


class EuPowerPricesConnectionError(EuPowerPricesApiError):
    """Timeout, connection failure, or a malformed/empty response."""


@dataclass(slots=True)
class PricePoint:
    """A single hourly price point."""

    ts_utc: datetime
    ts_local: datetime
    price_eur_mwh: float


@dataclass(slots=True)
class EuPowerPricesData:
    """Parsed forecast payload for one area."""

    area: str
    timezone: str
    currency: str
    unit: str
    generated_at: datetime
    series: list[PricePoint] = field(default_factory=list)


def _parse_iso(value: str) -> datetime:
    """Parse the API's `...Z` timestamps into aware datetimes."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class EuPowerPricesApiClient:
    """Wraps GET /v1/forecasts/{area}/latest."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, area: str) -> None:
        self._session = session
        self._api_key = api_key
        self._area = area

    @property
    def area(self) -> str:
        """Return the configured area code."""
        return self._area

    async def async_get_latest_forecast(self) -> EuPowerPricesData:
        """Fetch and parse the latest forecast for the configured area.

        Raises EuPowerPricesAuthError, EuPowerPricesAreaError, or
        EuPowerPricesConnectionError on failure; never returns partial data.
        """
        url = API_BASE_URL + API_FORECAST_PATH.format(area=self._area)
        headers = {HEADER_API_KEY: self._api_key}

        try:
            async with asyncio.timeout(TIMEOUT_SECONDS):
                async with self._session.get(url, headers=headers) as response:
                    if response.status in (401, 403):
                        raise EuPowerPricesAuthError("API key was rejected")
                    if response.status == 404:
                        raise EuPowerPricesAreaError(
                            f"Area '{self._area}' was not found"
                        )
                    if response.status != 200:
                        raise EuPowerPricesConnectionError(
                            f"Unexpected response status {response.status}"
                        )
                    try:
                        payload = await response.json()
                    except (aiohttp.ContentTypeError, ValueError) as err:
                        raise EuPowerPricesConnectionError(
                            "Response was not valid JSON"
                        ) from err
        except TimeoutError as err:
            raise EuPowerPricesConnectionError(
                "Timed out contacting the EU Power Prices API"
            ) from err
        except aiohttp.ClientError as err:
            raise EuPowerPricesConnectionError(f"Connection error: {err}") from err

        return self._parse_payload(payload)

    @staticmethod
    def _parse_payload(payload: dict) -> EuPowerPricesData:
        try:
            series_raw = payload["series"]
            if not series_raw:
                raise EuPowerPricesConnectionError("API returned an empty series")

            series = [
                PricePoint(
                    ts_utc=_parse_iso(point["ts_utc"]),
                    ts_local=_parse_iso(point["ts_local"]),
                    price_eur_mwh=float(point["price_eur_mwh"]),
                )
                for point in series_raw
            ]

            return EuPowerPricesData(
                area=payload["area"],
                timezone=payload["timezone"],
                currency=payload.get("currency", "EUR"),
                unit=payload.get("unit", "EUR/MWh"),
                generated_at=_parse_iso(payload["generated_at_utc"]),
                series=series,
            )
        except EuPowerPricesConnectionError:
            raise
        except (KeyError, TypeError, ValueError) as err:
            raise EuPowerPricesConnectionError(f"Malformed payload: {err}") from err
