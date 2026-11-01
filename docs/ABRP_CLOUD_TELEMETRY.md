# ABRP cloud telemetry

The connector forwards validated selected-vehicle telemetry to its existing paired
HTTPS Smart EV AI origin. It uses the existing connector token locally; ABRP
credentials never leave the Pi. No new pairing or inbound port is required.

When `CONNECTOR_ABRP_READONLY=true`, work polls advertise
`X-Smart-EV-Telemetry: abrp-fields-v1`. The cloud can queue the read-only
`abrp.fields` command with empty `params`. The connector rejects parameters and
reads only its fixed loopback adapter through `abrp.read_fields()`. The reply uses
the existing `/api/public/local-connectors/result` envelope (`request_id`,
`command`, `ok`, `data`, integer `latency_ms`). Failure sends a generic error with
no upstream details. This command is independent of `evcc.state` and manual control.

Data matches `/v1/abrp/fields`: selected vehicle ID, upstream fetch time, read-only
marker, bounded sanitized scalar field records, diagnostic connection booleans and
omitted field names. Each record retains its own measurement timestamp, provider,
unit, last-known value and availability. Upload time never refreshes measurement age.
The measurement maximum is 24 hours; adapter fetch age must remain within 15 minutes.
Unknown/missing timestamps are unavailable. Last-known values are display-only.

Location is included if supplied by ABRP, along with other available vehicle fields.
Cloud display must require owner authentication, remain private, and avoid external
map calls. ABRP telemetry must not authorize charging, alter evcc health, or replace
the fresh evcc state required for existing manual controls.

Deploy the matching cloud receiver before updating the connector. Older cloud
receivers simply ignore the additional capability header. Existing evcc vehicle
configuration and services do not need changing. Keep the installer's release
directory and use its rollback-connector.sh to restore the previous image/settings.
