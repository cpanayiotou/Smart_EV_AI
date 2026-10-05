# Smart EV Local Connector

Read-only bridge between Smart EV AI and an existing local evcc installation.

## Safety boundary

The connector only performs **HTTP GET** requests to evcc. It exposes local diagnostics:
- `GET /health`
- `GET /v1/evcc/state`

POST/PUT/PATCH/DELETE to the local connector return HTTP 405. There is no charger actuation code.

Cloud communication is outbound-only over HTTPS. The only cloud work command accepted in v0.2 is `evcc.state`. Unknown commands are rejected.

## Docker / NAS

1. Copy this directory to the home server/NAS.
2. Set `EVCC_URL` to the local evcc address.
3. Once cloud pairing endpoints are deployed, set `SMART_EV_CLOUD_URL` and a one-time `SMART_EV_PAIRING_CODE`.
4. Run `docker compose -f compose.example.yml up -d --build`.
5. Local diagnostics remain available at `http://<home-server>:7080/health`.

Do **not** port-forward 7070 or 7080 to the internet.

## Pairing

The connector initiates the pairing request. The cloud binds the one-time code to the signed-in owner and returns a scoped connector token. The token must then be persisted in the platform's secret store and supplied as `SMART_EV_CONNECTOR_TOKEN` on restart. Tokens are never printed.

See `cloud-api-contract.md` for the server contract.

## Current boundary

The local connector and outbound pairing client are implemented. The Smart EV cloud still needs the matching authenticated pairing/work/result endpoints before a real PWA connection can complete. Until then, the PWA must continue to show **Local connector required**.

The evcc `/api/state` structure mirrors evcc internal state and has no compatibility guarantee, so normalization belongs in Smart EV AI and must tolerate missing/changing fields.
