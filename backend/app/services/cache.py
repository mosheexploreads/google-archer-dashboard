"""
Tiny in-process TTL cache for dashboard aggregation results.

Dashboard data only changes when a sync or CSV upload writes to the DB, so we
cache query results and invalidate on every committed write (see the
after_commit hook in database.py). The TTL is just a safety backstop.

This is per-process; with a single uvicorn worker that covers the whole app.
"""
import threading
import time
from typing import Any, Callable

_lock = threading.Lock()
_store: dict = {}            # key -> (expires_at_monotonic, value)
_DEFAULT_TTL = 300.0         # seconds


def get_or_compute(key: Any, compute: Callable[[], Any], ttl: float = _DEFAULT_TTL) -> Any:
    """Return the cached value for `key`, or run `compute()`, store, and return it."""
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    # Compute outside the lock so a slow query doesn't block other keys.
    value = compute()
    with _lock:
        _store[key] = (now + ttl, value)
    return value


def clear() -> None:
    """Drop all cached entries. Called whenever the DB is written to."""
    with _lock:
        _store.clear()
