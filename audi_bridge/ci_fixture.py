"""Synthetic HTTP source for the evcc CI contract. Never contacts Audi."""
import time
from http.server import ThreadingHTTPServer
from bridge import Cache, handler_for

cache = Cache()
cache.update({'soc': 58, 'captured_at': time.time(), 'source': 'ci_fixture'})
ThreadingHTTPServer(('127.0.0.1', 7081), handler_for(cache)).serve_forever()
