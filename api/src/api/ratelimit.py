"""In-memory token buckets (one process). Swap for a shared store when running several instances."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic, max_keys: int = 100_000):
        self._clock = clock
        self._buckets: dict[tuple[str, str], tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def hit(self, bucket: str, key: str, per_minute: int) -> float:
        """Take one token. Returns 0 if allowed, else the seconds until one is available."""
        now = self._clock()
        rate = per_minute / 60.0
        with self._lock:
            if len(self._buckets) > self._max_keys:
                self._evict(now)
            tokens, last = self._buckets.get((bucket, key), (float(per_minute), now))
            tokens = min(float(per_minute), tokens + (now - last) * rate)
            if tokens >= 1:
                self._buckets[(bucket, key)] = (tokens - 1, now)
                return 0.0
            self._buckets[(bucket, key)] = (tokens, now)
            return (1 - tokens) / rate

    def _evict(self, now: float) -> None:
        # Drop buckets untouched for 10 minutes; they would be full again anyway.
        stale = [k for k, (_, last) in self._buckets.items() if now - last > 600]
        for k in stale:
            del self._buckets[k]
