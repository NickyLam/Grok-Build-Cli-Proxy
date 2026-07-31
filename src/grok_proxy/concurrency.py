from __future__ import annotations

import asyncio
from collections import defaultdict

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


class PerKeyConcurrencyTracker:
    """Per-API-key concurrent run limits (fail-fast 429)."""

    def __init__(self) -> None:
        self._in_flight: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    def in_flight_for(self, actor_id: str) -> int:
        return self._in_flight.get(actor_id, 0)

    async def acquire(self, actor_id: str, limit: int | None) -> None:
        """Acquire a slot for actor. limit=None means unlimited (only global gate applies)."""
        if limit is None or limit <= 0:
            return
        async with self._lock:
            current = self._in_flight[actor_id]
            if current >= limit:
                raise ProxyError(
                    f"Too many concurrent runs for this API key "
                    f"(max={limit}, in_flight={current}). Retry later.",
                    status_code=429,
                    code="key_max_concurrent",
                    details={"actor_id": actor_id, "limit": limit, "in_flight": current},
                )
            self._in_flight[actor_id] = current + 1

    async def release(self, actor_id: str, limit: int | None) -> None:
        if limit is None or limit <= 0:
            return
        async with self._lock:
            self._in_flight[actor_id] = max(0, self._in_flight[actor_id] - 1)
            if self._in_flight[actor_id] == 0:
                self._in_flight.pop(actor_id, None)

    def snapshot(self) -> dict[str, int]:
        return dict(self._in_flight)
