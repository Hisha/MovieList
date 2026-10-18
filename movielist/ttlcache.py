"""Tiny thread-safe TTL cache for short-lived in-memory memoization."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class TTLCache:
    """Memoize zero-argument call results for a fixed duration."""

    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._data: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: Any, factory: Callable[[], T]) -> T:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry and entry[0] > now:
                return entry[1]
        value = factory()
        with self._lock:
            self._data[key] = (time.monotonic() + self._ttl, value)
            if len(self._data) > 512:
                self._purge_locked(now)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def _purge_locked(self, now: float) -> None:
        for key, (expiry, _) in list(self._data.items()):
            if expiry <= now:
                self._data.pop(key, None)
