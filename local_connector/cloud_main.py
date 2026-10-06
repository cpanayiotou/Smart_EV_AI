"""Combined local HTTP health service + outbound Smart EV cloud pairing."""
from __future__ import annotations

import threading

import app
import pairing


def state_payload():
    status, state, latency = app._evcc_get("/api/state")
    if status != 200:
        raise RuntimeError(f"evcc returned HTTP {status}")
    return {
        "source": "evcc",
        "read_only": True,
        "observed_at_unix": app.time.time(),
        "latency_ms": round(latency, 1),
        "state": state,
    }


if __name__ == "__main__":
    server = app.ThreadingHTTPServer((app.LISTEN_HOST, app.LISTEN_PORT), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Local diagnostics listening on {app.LISTEN_HOST}:{app.LISTEN_PORT}")

    token = pairing.CONNECTOR_TOKEN
    poll_seconds = pairing.POLL_SECONDS
    if not token:
        token, poll_seconds = pairing.pair()
        # Deliberately don't print the token. Production packaging must persist it
        # in a secret store and provide SMART_EV_CONNECTOR_TOKEN on restart.
        print("Pairing succeeded. Store the connector token securely for restart.")
    pairing.run(token, state_payload, health_reader=app.health, poll_seconds=poll_seconds)
