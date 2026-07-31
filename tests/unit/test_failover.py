from __future__ import annotations

import pytest

from grok_proxy.backends.base import (
    BackendCapabilities,
    BackendError,
    BackendEvent,
    BackendSession,
    BackendSessionRequest,
    PromptInput,
)
from grok_proxy.backends.failover import FailoverBackend
from grok_proxy.backends.fake import FakeBackend


class BoomBackend:
    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(name="boom", supports_permissions=True)

    async def start_session(self, request: BackendSessionRequest) -> BackendSession:
        raise BackendError("acp down", code="acp_handshake_failed")

    async def send_prompt(self, session, prompt):
        raise NotImplementedError

    def events(self, session):
        raise NotImplementedError

    async def resolve_permission(self, session, decision):
        raise NotImplementedError

    async def cancel(self, session):
        pass

    async def close(self, session):
        pass


class FlakyBackend(BoomBackend):
    """Fails until `healthy` is flipped, then behaves like a FakeBackend."""

    def __init__(self) -> None:
        self.healthy = False
        self._inner = FakeBackend(
            script=[
                BackendEvent(type="text", data={"text": "acp"}),
                BackendEvent(type="end", data={"text": "acp"}),
            ]
        )

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(name="acp", supports_permissions=True)

    async def start_session(self, request: BackendSessionRequest) -> BackendSession:
        if not self.healthy:
            raise BackendError("acp down", code="acp_handshake_failed")
        return await self._inner.start_session(request)


@pytest.mark.asyncio
async def test_failover_to_fallback():
    fallback = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "fb"}),
            BackendEvent(type="end", data={"text": "fb"}),
        ]
    )
    fo = FailoverBackend(primary=BoomBackend(), fallback=fallback)
    req = BackendSessionRequest(model="m", cwd="/tmp")
    session = await fo.start_session(req)
    assert session.backend_name == "fake"
    assert fo.failover_count == 1
    await fo.send_prompt(session, PromptInput(text="hi"))
    events = [e async for e in fo.events(session)]
    assert any(e.type == "text" for e in events)


@pytest.mark.asyncio
async def test_failover_recovers_primary_after_cooldown(monkeypatch):
    """After the retry window the primary is probed again and re-adopted."""
    import grok_proxy.backends.failover as fo_mod

    primary = FlakyBackend()
    fallback = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "fb"}),
            BackendEvent(type="end", data={"text": "fb"}),
        ]
    )
    fo = FailoverBackend(primary=primary, fallback=fallback)
    req = BackendSessionRequest(model="m", cwd="/tmp")

    # Initial failure switches to fallback
    s1 = await fo.start_session(req)
    assert s1.backend_name == "fake"
    assert fo._use_fallback is True

    # Within the cooldown the primary is not retried even when healthy again
    primary.healthy = True
    s2 = await fo.start_session(req)
    assert s2.backend_name == "fake"
    assert fo._use_fallback is True

    # After the cooldown a new session probes the primary and switches back
    monkeypatch.setattr(fo_mod, "RETRY_PRIMARY_AFTER_SEC", 0.0)
    s3 = await fo.start_session(req)
    assert fo._use_fallback is False
    assert s3.backend_name == "fake"  # FlakyBackend delegates to a FakeBackend


@pytest.mark.asyncio
async def test_failover_retry_failure_stays_on_fallback(monkeypatch):
    import grok_proxy.backends.failover as fo_mod

    primary = FlakyBackend()  # stays unhealthy
    fallback = FakeBackend(
        script=[BackendEvent(type="end", data={"text": "fb"})]
    )
    fo = FailoverBackend(primary=primary, fallback=fallback)
    req = BackendSessionRequest(model="m", cwd="/tmp")
    await fo.start_session(req)
    monkeypatch.setattr(fo_mod, "RETRY_PRIMARY_AFTER_SEC", 0.0)
    s = await fo.start_session(req)
    assert s.backend_name == "fake"
    assert fo._use_fallback is True
