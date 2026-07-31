from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from grok_proxy.backends.acp import AcpBackend
from grok_proxy.backends.base import (
    BackendCapabilities,
    BackendEvent,
    BackendSession,
    BackendSessionRequest,
    PermissionDecisionPayload,
    PromptInput,
)
from grok_proxy.backends.headless import HeadlessBackend

logger = logging.getLogger(__name__)


class FailoverBackend:
    """Try primary (ACP); on handshake/start failure fall back to Headless."""

    def __init__(
        self,
        primary: AcpBackend | Any,
        fallback: HeadlessBackend | Any,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self._use_fallback = False
        self._caps = BackendCapabilities(
            name="auto",
            supports_permissions=True,
            supports_tools=True,
            supports_plan=True,
            supports_session_resume=True,
            supports_streaming=True,
        )
        self.failover_count = 0

    @property
    def capabilities(self) -> BackendCapabilities:
        if self._use_fallback:
            return self.fallback.capabilities
        return self._caps

    def _active(self) -> Any:
        return self.fallback if self._use_fallback else self.primary

    async def start_session(self, request: BackendSessionRequest) -> BackendSession:
        if self._use_fallback:
            return await self.fallback.start_session(request)
        try:
            return await self.primary.start_session(request)
        except Exception as e:  # noqa: BLE001
            logger.warning("ACP backend failed, failing over to headless: %s", e)
            self._use_fallback = True
            self.failover_count += 1
            session = await self.fallback.start_session(request)
            session.metadata["failover_from"] = "acp"
            session.metadata["failover_error"] = str(e)
            return session

    async def send_prompt(self, session: BackendSession, prompt: PromptInput) -> None:
        backend = self._backend_for(session)
        return await backend.send_prompt(session, prompt)

    def events(self, session: BackendSession) -> AsyncIterator[BackendEvent]:
        backend = self._backend_for(session)
        return backend.events(session)

    async def resolve_permission(
        self,
        session: BackendSession,
        decision: PermissionDecisionPayload,
    ) -> None:
        backend = self._backend_for(session)
        return await backend.resolve_permission(session, decision)

    async def cancel(self, session: BackendSession) -> None:
        backend = self._backend_for(session)
        return await backend.cancel(session)

    async def close(self, session: BackendSession) -> None:
        backend = self._backend_for(session)
        return await backend.close(session)

    def bind_response_id(self, session: BackendSession, response_id: str) -> None:
        backend = self._backend_for(session)
        bind = getattr(backend, "bind_response_id", None)
        if callable(bind):
            bind(session, response_id)

    def _backend_for(self, session: BackendSession) -> Any:
        if session.backend_name == "headless" or self._use_fallback:
            return self.fallback
        if session.backend_name == "acp":
            return self.primary
        # Prefer primary unless session was created under fallback
        if session.metadata.get("failover_from"):
            return self.fallback
        return self._active()


async def probe_acp_available(grok_bin: str, timeout: float = 3.0) -> bool:
    """Best-effort check whether `grok agent` is invocable."""
    import asyncio
    from shutil import which

    if not which(grok_bin):
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            grok_bin,
            "agent",
            "--help",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return False
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False
