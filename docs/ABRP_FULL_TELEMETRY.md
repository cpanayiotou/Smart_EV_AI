# Full ABRP telemetry feed

The adapter now reads the selected vehicle's whole `tlm` block rather than retaining only SoC. All finite numeric, boolean, null and bounded text fields are exported, including one level of nested telemetry such as `location.name`. Unknown scalar signals are retained with their original ABRP names; units are supplied only where verified from the reviewed upstream integration. Unsupported complex or oversized values are named in `omitted_fields`. Credentials/session/account envelopes and credential-like field names are never exported. Connection flags are separate diagnostics, not vehicle control commands.

This includes odometer, estimated battery range, power, voltage, current, speed, temperatures, battery capacity/health/energy, charging/plugged/driving flags, calibration data, firmware and location **when ABRP actually supplies them**. This does not create manufacturer readings or force an Enode refresh. GPS/location, if supplied, are visible on the trusted local connector page; do not share the full response publicly.

## Per-field contract

GET `/v1/abrp/fields` on the adapter (7081, loopback) and connector (7080) returns:

```json
{"fields":{"odometer":{"last_known_value":12345,"value":12345,"unit":"km","timestamp":1793554911,"provider":"enode","age_seconds":100,"max_age_seconds":86400,"stale":false,"available":true}}}
```

The example is synthetic. Each field uses **its own measurement timestamp**. A missing timestamp/provider never inherits the SoC timestamp, latest vehicle time or request time. Missing timestamps are shown as unknown and the field remains display-only. Values older than 24 hours stay visible as last-known values but have `value: null`. Regressing timestamps, revoked authorization, invalid values and stopped/failed polling block scalar use. A missing SoC does not hide a valid odometer. UI text is inserted as text, not HTML.

Connection diagnostics include boolean connection/asleep/authorization flags from the selected vehicle. These are snapshot diagnostics without a claimed per-field measurement time. Measurements stay in ABRP units: odometer/range in km, power in kW, SoE in Wh, capacity in kWh, voltage in V, current in A, temperature in °C. Unknown units remain null rather than being guessed.

## evcc

The [evcc custom vehicle interface](https://docs.evcc.io/en/user-defined-devices/#vehicle) supports odometer and range in km. This update adds numeric GET endpoints `/v1/abrp/odometer` and `/v1/abrp/range`. They return HTTP 503 (not zero) if the field is absent, invalid, over 24 hours old, missing its own timestamp/source, or the upstream poll is unavailable. No authentication credentials are needed by evcc for these trusted-LAN routes.

After installing, test on the Pi:

```sh
curl --max-time 5 -i http://127.0.0.1:7080/v1/abrp/odometer
curl --max-time 5 -i http://127.0.0.1:7080/v1/abrp/range
```

Only add the blocks that return HTTP 200 with a valid reading to the existing evcc user-defined vehicle:

```yaml
odometer:
  source: http
  uri: http://10.1.1.71:7080/v1/abrp/odometer
  timeout: 5s
range:
  source: http
  uri: http://10.1.1.71:7080/v1/abrp/range
  timeout: 5s
```

Keep the existing SoC block and confirmed `capacity: 86.5`. The adapter installer does not edit evcc. A missing optional field must not be replaced with a fabricated zero. The connector table shows what is actually reported, including unknown-age values and unsupported field names. Other telemetry has no direct evcc vehicle mapping and remains available through this table/JSON API. No derived charging status is inferred from a 24-hour-old plugged/charging flag.

The guided installer retains authorization and the selected vehicle, upgrades only recognized adapter versions, and rebuilds the non-root connector with the existing startup/readability checks. It preserves paired data and manual-control settings. No PR merge, charger command or evcc configuration write is performed by this release.
