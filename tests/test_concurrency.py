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
