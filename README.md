# EU Power Prices for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A custom Home Assistant integration for [api.eupowerprices.com](https://api.eupowerprices.com),
exposing day-ahead / multi-day electricity price forecasts as a sensor —
configured entirely through the UI, no YAML required.

Built against the requirements in `docs/requirements.md` (or wherever you've
kept that file) — see that doc for the full design rationale, including the
Phase 2 backlog (cheapest-hour sensor, negative-price binary sensor, Energy
Dashboard cost sensor) that was deliberately deferred out of this v1.

## What you get

Per configured market area, one device with one entity:

- **`sensor.<area>_current_price`** — the price (in the API's native unit,
  `EUR/MWh`) for the current local hour.
  - Attribute `forecast`: the next 10 days as `{ts_local, price}` pairs —
    enough to drive a forecast chart card.
  - Attribute `forecast_history`: the last 24 successful fetches, each with a
    full future forecast series. This is useful for charts that overlay a new
    line on every poll and fade older lines out.
  - Attributes `generated_at`, `currency`, `area`.

You can add the integration multiple times, once per market area (e.g. NL
and DE side by side) — each is a separate config entry.

## Installation

### Via HACS (custom repository)

1. HACS → Integrations → ⋮ → **Custom repositories**.
2. Add this repository's URL, category **Integration**.
3. Install **EU Power Prices**, then restart Home Assistant.

### Manual

Copy `custom_components/eu_power_prices/` into your Home Assistant
`config/custom_components/` directory, then restart.

## Configuration

Settings → Devices & Services → **Add Integration** → search for
**EU Power Prices**.

1. Enter your API key.
2. Pick a market area from the dropdown, or type a code if yours isn't
   listed — the API call to validate that combination happens immediately,
   so you'll know right away if either was wrong.

If your API key is later rejected (e.g. it expired), Home Assistant will
prompt you to re-authenticate from the integration's card — no need to
delete and re-add it.

### Options

Settings → Devices & Services → EU Power Prices → **Configure** lets you
change the polling interval (15–180 minutes, default 60 — matches how often
the upstream API regenerates its forecast).

## Example: charting the forecast

The `forecast` attribute pairs well with a card like
[ApexCharts Card](https://github.com/RomRider/apexcharts-card) (install via
HACS separately):

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: NL Power Price Forecast
series:
  - entity: sensor.nl_current_price
    data_generator: |
      return entity.attributes.forecast.map(point => {
        return [new Date(point.ts_local).getTime(), point.price];
      });
```

If you want to overlay multiple forecast lines, use `forecast_history` and
map each snapshot to its own series. Each history item includes
`generated_at`, `series`, `timezone`, `currency`, and `area`.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: NL Power Price Forecast History
graph_span: 10d
span:
  start: day
series:
  - entity: sensor.nl_current_price
    name: Latest forecast
    type: line
    stroke_width: 3
    opacity: 0.9
    data_generator: |
      return entity.attributes.forecast.map(point => [
        new Date(point.ts_local).getTime(),
        point.price,
      ]);
  - entity: sensor.nl_current_price
    name: Previous forecast
    type: line
    stroke_width: 2
    opacity: 0.25
    data_generator: |
      const history = entity.attributes.forecast_history ?? [];
      const snapshot = history.at(-2);
      if (!snapshot) return [];

      return snapshot.series.map(point => [
        new Date(point.ts_local).getTime(),
        point.price,
      ]);
  - entity: sensor.nl_current_price
    name: Older forecast
    type: line
    stroke_width: 1
    opacity: 0.12
    data_generator: |
      const history = entity.attributes.forecast_history ?? [];
      const snapshot = history.at(-3);
      if (!snapshot) return [];

      return snapshot.series.map(point => [
        new Date(point.ts_local).getTime(),
        point.price,
      ]);
```

The `forecast_history` attribute is intentionally bounded, so you can keep the
last few polls on screen without growing the entity state forever. If you want
more faded lines, clone the last two series blocks and change the `at(-N)`
index to match the snapshot you want to display.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Config flow shows "Invalid API key" | The key was rejected by the API (HTTP 401/403). Double-check it was copied correctly. |
| Config flow shows "That area code wasn't recognized" | The API returned 404 for that area code (HTTP 404). Confirm the code with the vendor — only a partial list is offered in the dropdown. |
| Entity goes `unavailable` | The integration treats timeouts/connection errors as transient and retries on the normal schedule; sustained unavailability means the API has been unreachable across several consecutive polls. Check the API status and your network. |
| Asked to re-authenticate | The API key stopped working after initial setup (e.g. revoked or expired) — enter a new one, the area stays as configured. |

Diagnostics (Settings → Devices & Services → EU Power Prices → device →
**Download diagnostics**) include the last successful payload's metadata
with the API key redacted — useful when filing an issue.

## Contributing

Issues and PRs welcome. Please run `pytest` (see `requirements_test.txt`)
before submitting.

## License

MIT — see `LICENSE`.
