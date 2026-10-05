# Smart EV Local Connector

Read-only local bridge between Smart EV AI and an existing evcc installation.

## Safety boundary

The connector only performs **HTTP GET** requests to evcc. It exposes:
- `GET /health`
- `GET /v1/evcc/state`

All POST/PUT/PATCH/DELETE requests to the connector return HTTP 405. There is no charger actuation code.

## Docker

evcc's current Docker documentation recommends host networking on Linux/NAS systems because it improves LAN discovery and device reachability. The example therefore uses host networking.

1. Copy this directory to the home server/NAS.
2. Set `EVCC_URL` to the local evcc address.
3. Run `docker compose -f compose.example.yml up -d --build`.
4. Open `http://<home-server>:7080/health`.

A connection is considered verified only when evcc returns a recognizable `/api/state` object.

## Current boundary

This is the local read-only half of the connection. It does **not** expose the connector to the public internet and does not contain a cloud pairing secret. A secure outbound pairing/relay to the Smart EV AI cloud is the next layer; until that exists, the cloud PWA must continue to show “Local connector required”.

The evcc `/api/state` structure mirrors evcc's internal UI state and has no compatibility guarantee, so normalization belongs in Smart EV AI and must tolerate missing/changing fields.
