from __future__ import annotations

import pytest

from grok_proxy.concurrency import PerKeyConcurrencyTracker
from grok_proxy.errors import ProxyError


@pytest.mark.asyncio
async def test_per_key_limit():
    t = PerKeyConcurrencyTracker()
    await t.acquire("k1", 1)
    with pytest.raises(ProxyError) as ei:
        await t.acquire("k1", 1)
    assert ei.value.code == "key_max_concurrent"
    # other keys independent
    await t.acquire("k2", 1)
    await t.release("k1", 1)
    await t.acquire("k1", 1)
    await t.release("k1", 1)
    await t.release("k2", 1)


@pytest.mark.asyncio
async def test_unlimited_when_none():
    t = PerKeyConcurrencyTracker()
    await t.acquire("k", None)
    await t.acquire("k", None)
    assert t.in_flight_for("k") == 0
