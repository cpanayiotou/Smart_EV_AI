# Cloud protocol used by the local connector (v0.2)

Reviewed against pairing.py and test_pairing.py on local-connector-readonly.
The backend in this repository does not implement these endpoints. Live cloud
compatibility remains a deployment check; do not infer it from service liveness.

All requests are outbound HTTPS with normal certificate validation, no environment
proxy inheritance and no redirects. Cloud API configuration is an HTTPS origin.

* POST `/api/public/local-connectors/pair`: sends `pairing_code`,
  `connector_version: "0.2"`, `capabilities: ["evcc.health", "evcc.state"]`,
  `read_only: true`. Expects a nonempty `token` and optional `poll_interval_s`.
* GET `/api/public/local-connectors/work`: bearer authorization. Expects
  `requests: [{request_id, command}]` (empty list when idle), optional
  `poll_interval_s`. Poll interval is at least five seconds.
* POST `/api/public/local-connectors/result`: bearer authorization. Sends
  `request_id`, `command`, `ok`, and `data` plus `latency_ms` on success or a
  sanitized `error` on failure. State data retains the existing read-only envelope.

Only evcc.health and evcc.state are accepted. All evcc traffic is GET /api/state.
Unknown cloud commands receive unsupported_read_only_command, without actuation.
Older documentation's non-public paths, connector_token and payload response
fields were stale and are not used.

The cloud must enforce expiring single-use owner-bound codes, rate limits,
scoped token hashes, revocation, work ownership/freshness and result size limits.
These server guarantees cannot be verified from this repository. Before rollout,
verify a fresh pairing, idle/work/result cycle, restart and revocation against the
intended deployment, without sending charger commands.
