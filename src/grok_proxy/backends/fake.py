from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from grok_proxy.backends.base import (
    BackendCapabilities,
    BackendError,
    BackendEvent,
    BackendSession,
    BackendSessionRequest,
    PermissionDecisionPayload,
    PromptInput,
)


@dataclass
class _FakeHandle:
    request: BackendSessionRequest
    prompt: str | None = None
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    permission_queue: asyncio.Queue[PermissionDecisionPayload] = field(
        default_factory=asyncio.Queue
    )


EventScript = list[BackendEvent] | Callable[[str], list[BackendEvent] | AsyncIterator[BackendEvent]]


class FakeBackend:
    """Deterministic backend for unit/integration tests."""

    def __init__(
        self,
        script: list[BackendEvent] | None = None,
        *,
        script_factory: Callable[[str], list[BackendEvent]] | None = None,
        delay_sec: float = 0.0,
    ) -> None:
        self._script = script or [
            BackendEvent(type="text", data={"text": "hello from fake"}),
            BackendEvent(
                type="end",
                data={
                    "session_id": "fake-session",
                    "stop_reason": "EndTurn",
                    "num_turns": 1,
                    "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                    "text": "hello from fake",
                },
            ),
        ]
        self.script_factory = script_factory
        self.delay_sec = delay_sec
        self.started: list[BackendSessionRequest] = []
        self.prompts: list[str] = []
        self.cancelled: list[str] = []
        self.decisions: list[PermissionDecisionPayload] = []
        self._caps = BackendCapabilities(
            name="fake",
            supports_permissions=True,
            supports_tools=True,
            supports_plan=True,
            supports_session_resume=True,
            supports_streaming=True,
        )

    @property
    def capabilities(self) -> BackendCapabilities:
        return self._caps

    async def start_session(self, request: BackendSessionRequest) -> BackendSession:
        self.started.append(request)
        sid = request.session_id or f"fake_{uuid.uuid4().hex[:12]}"
        return BackendSession(
            session_id=sid,
            backend_name="fake",
            cwd=request.cwd,
            model=request.model,
            handle=_FakeHandle(request=request),
        )

    async def send_prompt(self, session: BackendSession, prompt: PromptInput) -> None:
        handle = self._handle(session)
        handle.prompt = prompt.text
        self.prompts.append(prompt.text)

    async def events(self, session: BackendSession) -> AsyncIterator[BackendEvent]:
        handle = self._handle(session)
        if handle.prompt is None:
            raise BackendError("no prompt", code="no_prompt")
        events = self._script
        if self.script_factory is not None:
            events = self.script_factory(handle.prompt)
        for ev in events:
            if handle.cancel.is_set():
                yield BackendEvent(type="error", data={"message": "cancelled", "code": "cancelled"})
                return
            if self.delay_sec:
                await asyncio.sleep(self.delay_sec)
            if ev.type == "permission_request":
                # Emit first so orchestrator can create pending permission,
                # then block until resolve_permission (or cancel).
                yield ev
                wait_task = asyncio.create_task(handle.permission_queue.get())
                cancel_task = asyncio.create_task(handle.cancel.wait())
                done, pending = await asyncio.wait(
                    {wait_task, cancel_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                if cancel_task in done and handle.cancel.is_set():
                    yield BackendEvent(
                        type="error", data={"message": "cancelled", "code": "cancelled"}
                    )
                    return
                continue
            yield ev

    async def resolve_permission(
        self,
        session: BackendSession,
        decision: PermissionDecisionPayload,
    ) -> None:
        self.decisions.append(decision)
        self._handle(session).permission_queue.put_nowait(decision)

    async def cancel(self, session: BackendSession) -> None:
        self.cancelled.append(session.session_id)
        self._handle(session).cancel.set()

    async def close(self, session: BackendSession) -> None:
        self._handle(session).cancel.set()

    def _handle(self, session: BackendSession) -> _FakeHandle:
        if not isinstance(session.handle, _FakeHandle):
            raise BackendError("bad fake handle", code="bad_session")
        return session.handle
