"""Small in-process sliding-window rate limiter.

This is intentionally simple. For multi-worker deployments swap in Redis; the
call sites only use ``check``.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Deque

from app.core.errors import RateLimitError


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._last_cleanup = time.monotonic()

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets[key]
            cutoff = now - window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                raise RateLimitError(
                    "Too many requests. Please try again later.",
                    details={"retry_after_seconds": retry_after},
                )
            bucket.append(now)
            if now - self._last_cleanup > 300:
                self._cleanup(now)
                self._last_cleanup = now

    def _cleanup(self, now: float) -> None:
        stale = [key for key, bucket in self._buckets.items() if not bucket or bucket[-1] < now - 3600]
        for key in stale:
            self._buckets.pop(key, None)

    async def reset(self) -> None:
        async with self._lock:
            self._buckets.clear()


rate_limiter = InMemoryRateLimiter()
