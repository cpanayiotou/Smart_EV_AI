# Smart EV cloud pairing API contract (v0.2)

This document defines the server-side endpoints still required by the Smart EV AI cloud.

## Security model

- Connector initiates all traffic outbound over HTTPS.
- No router port-forward and no public evcc/connector port.
- User requests a short-lived, one-time pairing code while authenticated.
- Pairing code is bound server-side to that authenticated owner and expires quickly.
- Successful pairing returns a long random connector token. Store only a hash server-side.
- Connector token is scoped to one owner/connector and read-only capabilities.
- Revoke/rotate from Integrations.
- Rate-limit pairing and polling. Audit pairing/revocation.
- Never return another owner's work/results.

## Endpoints

### POST /api/local-connectors/pair

Input:
```json
{"pairing_code":"123456","connector_version":"0.2","capabilities":["evcc.health","evcc.state"],"read_only":true}
```

Output:
```json
{"connector_token":"<one-time-secret>"}
```

### GET /api/local-connectors/work

Authorization: `Bearer <connector_token>`

Output when idle:
```json
{"command":"none"}
```

Allowed work in v0.2:
```json
{"request_id":"uuid","command":"evcc.state"}
```

No charger-control command is valid in v0.2.

### POST /api/local-connectors/result

Authorization: connector bearer token.

Input:
```json
{"request_id":"uuid","ok":true,"payload":{"source":"evcc","read_only":true,"state":{}}}
```

Server validates request ownership, freshness, payload size and read-only capability before accepting.

## PWA flow

1. Authenticated user presses **Connect evcc**.
2. Cloud creates a one-time pairing code.
3. User enters the code into the local connector setup (or installer passes it once).
4. Connector pairs outbound.
5. PWA sees connector online and requests an `evcc.state` read.
6. Existing normalization/import logic maps evcc entities.
7. PWA shows **Connected** only after verified state is received.
