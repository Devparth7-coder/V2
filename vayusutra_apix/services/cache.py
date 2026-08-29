"""
VayuSutra APIx - In-Process TTL Cache
Simple thread-safe time-to-live cache used to avoid expensive recalculation on every
dashboard request. SQLite + in-process cache is sufficient for the SIH demo; no Redis needed.
"""
import threading
import time
from typing import Any, Callable, Optional, Dict, Tuple


class TTLCache:
    def __init__(self, default_ttl_seconds: float = 60.0):
        self._default_ttl = default_ttl_seconds
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, value = item
            if time.time() > expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        ttl = self._default_ttl if ttl_seconds is None else ttl_seconds
        with self._lock:
            self._store[key] = (time.time() + ttl, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def get_or_compute(self, key: str, compute_fn: Callable[[], Any],
                       ttl_seconds: Optional[float] = None) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = compute_fn()
        self.set(key, value, ttl_seconds)
        return value

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# Global in-process cache
api_cache = TTLCache(default_ttl_seconds=45.0)
