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
