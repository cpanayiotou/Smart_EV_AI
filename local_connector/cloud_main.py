"""LAN setup service and outbound read-only cloud worker."""
import os
import threading
import app
import pairing
from setup_web import Handler, Setup, local_address


def state_payload():
    status, state, latency = app._evcc_get('/api/state')
    if status != 200:
        raise RuntimeError('evcc unavailable')
    return {'source': 'evcc', 'read_only': True, 'observed_at_unix': app.time.time(),
            'latency_ms': round(latency, 1), 'state': state}


def start_worker(token, interval, callback):
    threading.Thread(target=pairing.run, args=(token, state_payload),
                     kwargs={'health_reader': app.health, 'poll_seconds': interval,
                             'status_callback': callback}, daemon=True).start()


if __name__ == '__main__':
    host = os.getenv('CONNECTOR_HOST', '127.0.0.1')
    if not local_address(host):
        raise SystemExit('CONNECTOR_HOST must be an explicit loopback or private LAN IP')
    state = Setup(os.getenv('CONNECTOR_DATA_DIR', '/data'), start_worker)
    server = app.ThreadingHTTPServer((host, app.LISTEN_PORT), Handler)
    server.setup_state = state
    print('Smart EV read-only setup service ready; use the local setup-password file.')
    server.serve_forever()
