from __future__ import annotations

import asyncio
import logging
import os
import signal
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TrackedProcess:
    response_id: str
    proc: asyncio.subprocess.Process
    metadata: dict[str, Any] = field(default_factory=dict)


class ProcessManager:
    """Track Grok child processes / process groups for cancel and shutdown."""

    def __init__(self) -> None:
        self._procs: dict[str, TrackedProcess] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        response_id: str,
        proc: asyncio.subprocess.Process,
        **metadata: Any,
    ) -> None:
        async with self._lock:
            self._procs[response_id] = TrackedProcess(
                response_id=response_id,
                proc=proc,
                metadata=dict(metadata),
            )

    async def unregister(self, response_id: str) -> None:
        async with self._lock:
            self._procs.pop(response_id, None)

    async def stop(self, response_id: str, *, force: bool = False) -> None:
        async with self._lock:
            tracked = self._procs.get(response_id)
        if not tracked:
            return
        await self._terminate(tracked.proc, force=force)
        await self.unregister(response_id)

    async def stop_all(self, *, force: bool = False) -> None:
        async with self._lock:
            items = list(self._procs.values())
            self._procs.clear()
        for tracked in items:
            await self._terminate(tracked.proc, force=force)

    @staticmethod
    async def _terminate(proc: asyncio.subprocess.Process, *, force: bool = False) -> None:
        if proc.returncode is not None:
            return
        sig = signal.SIGKILL if force else signal.SIGTERM
        try:
            if os.name != "nt" and proc.pid:
                try:
                    os.killpg(proc.pid, sig)
                except (ProcessLookupError, PermissionError, OSError):
                    if force:
                        proc.kill()
                    else:
                        proc.terminate()
            else:
                if force:
                    proc.kill()
                else:
                    proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            if not force:
                await ProcessManager._terminate(proc, force=True)
            else:
                try:
                    await proc.wait()
                except Exception:  # noqa: BLE001
                    logger.exception("failed waiting for killed process")
