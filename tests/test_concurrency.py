from __future__ import annotations

import asyncio

import pytest

from grok_proxy.concurrency import ConcurrencyGate
from grok_proxy.errors import ProxyError


@pytest.mark.asyncio
async def test_gate_fail_fast():
    gate = ConcurrencyGate(1)
    await gate.acquire()
    with pytest.raises(ProxyError) as ei:
        await gate.acquire()
    assert ei.value.status_code == 429
    await gate.release()
    await gate.acquire()
    await gate.release()


@pytest.mark.asyncio
async def test_gate_no_toctou_overshoot():
    """Concurrent acquires must never exceed the limit (atomic check+increment)."""
    limit = 2
    gate = ConcurrencyGate(limit)

    async def try_acquire() -> bool:
        try:
            await gate.acquire()
            return True
        except ProxyError:
            return False

    results = await asyncio.gather(*[try_acquire() for _ in range(20)])
    assert sum(results) == limit
    assert gate.in_flight == limit
    for _ in range(limit):
        await gate.release()
    assert gate.in_flight == 0
