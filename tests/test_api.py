"""Tests for custom_components.eu_power_prices.api.

These mock the aiohttp session directly so they run without any network
access and without depending on the live API's current behavior.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from custom_components.eu_power_prices.api import (
    EuPowerPricesApiClient,
    EuPowerPricesAreaError,
    EuPowerPricesAuthError,
    EuPowerPricesConnectionError,
)


class _FakeResponse:
    """Stands in for an aiohttp ClientResponse used as `async with ...`."""

    def __init__(self, status: int, json_data=None, json_exc: Exception | None = None):
        self.status = status
        self._json_data = json_data
        self._json_exc = json_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._json_data


class _FakeSession:
    """Stands in for aiohttp.ClientSession; `get()` returns the canned response."""

    def __init__(self, response):
        self._response = response

    def get(self, url, headers=None):
        return self._response


@pytest.mark.asyncio
async def test_parses_valid_payload(sample_forecast_payload):
    """A 200 response with a well-formed payload parses cleanly."""
    session = _FakeSession(_FakeResponse(200, json_data=sample_forecast_payload))
    client = EuPowerPricesApiClient(session=session, api_key="key", area="NL")

    data = await client.async_get_latest_forecast()

    assert data.area == "NL"
    assert data.currency == "EUR"
    assert data.unit == "EUR/MWh"
    assert data.generated_at == datetime(2026, 6, 25, 18, 0, tzinfo=UTC)
    assert len(data.series) == 5
    assert data.series[0].price_eur_mwh == 141.7
    assert data.series[0].ts_utc == datetime(2026, 6, 25, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_401_raises_auth_error():
    """A rejected API key maps to EuPowerPricesAuthError."""
    session = _FakeSession(_FakeResponse(401))
    client = EuPowerPricesApiClient(session=session, api_key="bad", area="NL")

    with pytest.raises(EuPowerPricesAuthError):
        await client.async_get_latest_forecast()


@pytest.mark.asyncio
async def test_403_also_raises_auth_error():
    """403 is treated the same as 401 per the requirements' error table."""
    session = _FakeSession(_FakeResponse(403))
    client = EuPowerPricesApiClient(session=session, api_key="bad", area="NL")

    with pytest.raises(EuPowerPricesAuthError):
        await client.async_get_latest_forecast()


@pytest.mark.asyncio
async def test_404_raises_area_error():
    """An unrecognized area maps to EuPowerPricesAreaError."""
    session = _FakeSession(_FakeResponse(404))
    client = EuPowerPricesApiClient(session=session, api_key="key", area="XX")

    with pytest.raises(EuPowerPricesAreaError):
        await client.async_get_latest_forecast()


@pytest.mark.asyncio
async def test_other_status_raises_connection_error():
    """A 500, or anything not explicitly mapped, is treated as transient."""
    session = _FakeSession(_FakeResponse(500))
    client = EuPowerPricesApiClient(session=session, api_key="key", area="NL")

    with pytest.raises(EuPowerPricesConnectionError):
        await client.async_get_latest_forecast()


@pytest.mark.asyncio
async def test_empty_series_raises_connection_error(sample_forecast_payload):
    """An empty series is treated as a bad/transient response, not a crash."""
    payload = {**sample_forecast_payload, "series": []}
    session = _FakeSession(_FakeResponse(200, json_data=payload))
    client = EuPowerPricesApiClient(session=session, api_key="key", area="NL")

    with pytest.raises(EuPowerPricesConnectionError):
        await client.async_get_latest_forecast()


@pytest.mark.asyncio
async def test_malformed_payload_raises_connection_error(sample_forecast_payload):
    """A missing required field is caught and re-raised as our own error type."""
    payload = dict(sample_forecast_payload)
    del payload["area"]
    session = _FakeSession(_FakeResponse(200, json_data=payload))
    client = EuPowerPricesApiClient(session=session, api_key="key", area="NL")

    with pytest.raises(EuPowerPricesConnectionError):
        await client.async_get_latest_forecast()


@pytest.mark.asyncio
async def test_bad_json_raises_connection_error():
    """A 200 response that fails to decode as JSON is treated as transient."""
    session = _FakeSession(
        _FakeResponse(200, json_exc=ValueError("not json"))
    )
    client = EuPowerPricesApiClient(session=session, api_key="key", area="NL")

    with pytest.raises(EuPowerPricesConnectionError):
        await client.async_get_latest_forecast()


class _FakeContextThatRaises:
    """A session.get() return value whose __aenter__ raises immediately."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *exc_info):
        return False


class _FakeSessionThatRaises:
    """An aiohttp session stub that raises on every GET."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def get(self, url, headers=None):
        return _FakeContextThatRaises(self._exc)


@pytest.mark.asyncio
async def test_timeout_raises_connection_error():
    """A TimeoutError from the network layer maps to EuPowerPricesConnectionError."""
    import aiohttp

    client = EuPowerPricesApiClient(
        session=_FakeSessionThatRaises(TimeoutError()),
        api_key="key",
        area="NL",
    )

    with pytest.raises(EuPowerPricesConnectionError, match="Timed out"):
        await client.async_get_latest_forecast()


@pytest.mark.asyncio
async def test_aiohttp_client_error_raises_connection_error():
    """A low-level aiohttp error maps to EuPowerPricesConnectionError."""
    import aiohttp

    client = EuPowerPricesApiClient(
        session=_FakeSessionThatRaises(aiohttp.ClientError("connection refused")),
        api_key="key",
        area="NL",
    )

    with pytest.raises(EuPowerPricesConnectionError, match="Connection error"):
        await client.async_get_latest_forecast()
