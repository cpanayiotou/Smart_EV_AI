"""LAN setup and outbound worker, with optional authorized manual control."""
import os
import threading
import app
import pairing
from setup_web import Handler, Setup, local_address


def state_payload():
    status, state, latency = app._evcc_get('/api/state')
    if status != 200:
        raise RuntimeError('evcc unavailable')
    if not isinstance(state, dict):
        raise ValueError('Invalid evcc state response')
    return state


def start_worker(token, interval, callback):
    threading.Thread(target=pairing.run, args=(token, state_payload),
                     kwargs={'health_reader': app.health, 'poll_seconds': interval,
                             'status_callback': callback}, daemon=True).start()


if __name__ == '__main__':
    host = os.getenv('CONNECTOR_HOST', '0.0.0.0')
    if host != '0.0.0.0' and not local_address(host):
        raise SystemExit('CONNECTOR_HOST must be 0.0.0.0, loopback or a private LAN IP')
    state = Setup(os.getenv('CONNECTOR_DATA_DIR', '/data'), start_worker)
    server = app.ThreadingHTTPServer((host, app.LISTEN_PORT), Handler)
    server.setup_state = state
    print('Smart EV setup service ready; open / or /setup on your LAN.')
    server.serve_forever()
