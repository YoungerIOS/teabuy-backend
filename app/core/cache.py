from __future__ import annotations

import time
from threading import Lock
from typing import Any, Callable


class TTLCache:
    def __init__(self, default_ttl: int = 30, max_size: int = 1024) -> None:
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._lock = Lock()
        self._store: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        now = time.monotonic()
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at <= now:
                del self._store[key]
                return None
            return value

    def set(self, key: Any, value: Any, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + (ttl if ttl is not None else self.default_ttl)
        with self._lock:
            if len(self._store) >= self.max_size:
                self._store.clear()
            self._store[key] = (expires_at, value)

    def get_or_set(self, key: Any, ttl: int, factory: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value, ttl)
        return value
