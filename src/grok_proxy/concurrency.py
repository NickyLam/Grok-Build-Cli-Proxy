from __future__ import annotations

import asyncio

from grok_proxy.errors import ProxyError


class ConcurrencyGate:
    """Fail-fast semaphore: reject with 429 when at capacity (no queue)."""

    def __init__(self, limit: int) -> None:
        self._limit = max(1, limit)
        self._sem = asyncio.Semaphore(self._limit)
        self._in_flight = 0
        self._lock = asyncio.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def in_flight(self) -> int:
        return self._in_flight

    async def acquire(self) -> None:
        if self._sem.locked():
            raise ProxyError(
                f"Too many concurrent Grok runs (max={self._limit}). Retry later.",
                status_code=429,
                code="max_concurrent",
            )
        await self._sem.acquire()
        async with self._lock:
            self._in_flight += 1

    async def release(self) -> None:
        async with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
        self._sem.release()

    async def __aenter__(self) -> ConcurrencyGate:
        await self.acquire()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.release()
