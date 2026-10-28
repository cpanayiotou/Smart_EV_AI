# Cloud protocol used by the local connector (v0.2)

Reviewed against the Lovable cloud protocol.ts and service.ts on 2026-10-28,
plus pairing.py and the connector tests. The previous client contract was incorrect.
The backend in this repository does not implement these endpoints. Live cloud
compatibility remains a deployment check; do not infer it from service liveness.

All requests are outbound HTTPS with normal certificate validation, no environment
proxy inheritance and no redirects. Cloud API configuration is an HTTPS origin.

* POST `/api/public/local-connectors/pair`: sends `code` and `version: "0.2"`. The strict server schema allows only
  those fields and optional `name`; do not send capabilities or read_only. Expects a nonempty `token` and optional `poll_interval_s`.
* GET `/api/public/local-connectors/work`: bearer authorization. Expects
  `requests: [{id, command, params}]` (empty list when idle), optional
  `poll_interval_s`. Poll interval is at least five seconds.
* POST `/api/public/local-connectors/result`: bearer authorization. Sends
  `request_id`, `command`, `ok`, and `data` plus `latency_ms` on success or a
  sanitized `error` on failure. State data is the raw evcc state (or its upstream result wrapper), without a
  connector envelope. latency_ms is an integer from 0 to 600000. Error is an
  object with code: auth_required, unreachable, timeout, or invalid_response.

Only evcc.health and evcc.state are accepted. All evcc traffic is GET /api/state.
Unknown cloud commands are ignored without an evcc read or actuation.
Older documentation's non-public paths, connector_token and payload response
fields were stale and are not used.

The cloud must enforce expiring single-use owner-bound codes, rate limits,
scoped token hashes, revocation, work ownership/freshness and result size limits.
These server guarantees cannot be verified from this repository. Before rollout,
verify a fresh pairing, idle/work/result cycle, restart and revocation against the
intended deployment, without sending charger commands.

## v0.3 optional manual control extension

Telemetry remains v0.2-compatible. Pairing version is 0.3. With local
CONNECTOR_ALLOW_CONTROL=true, work polling includes X-Smart-EV-Control: mode-v1.
Only evcc.set_mode is added, separately from the read allowlist. Work params are
exactly {loadpoint: integer 1..20, mode: off|now, expires_at: ISO UTC}, with a
maximum 60-second cloud lifetime. Before a write, the connector POSTs
/api/public/local-connectors/authorize with bearer token and {request_id: UUID}.
Only {authorized:true} allows execution; the cloud must atomically consume a
one-use grant, checking owner, connector, switch, capability, state, and expiry.
The result data is {loadpoint, mode, verified:true} only after GET state confirms
mode. Expired, denied, duplicate or malformed commands never write to evcc.

The local replay journal is durable before authorization and execution. An
ambiguous failure is never automatically retried. Cloud switch OFF prevents new
grants but cannot retract an already issued grant; it does not mean Stop.
