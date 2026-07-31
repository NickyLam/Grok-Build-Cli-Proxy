from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TrackedProcess:
    response_id: str
    proc: asyncio.subprocess.Process
    metadata: dict[str, Any] = field(default_factory=dict)


class ProcessManager:
    """Track Grok child processes / process groups for cancel and shutdown."""

    def __init__(self, state_path: str | Path | None = None) -> None:
        self._procs: dict[str, TrackedProcess] = {}
        self._lock = asyncio.Lock()
        self.state_path = Path(
            state_path
            or Path.home() / ".grok-proxy" / "run" / "child_pids.json"
        )
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

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
            self._persist_unlocked()

    async def unregister(self, response_id: str) -> None:
        async with self._lock:
            self._procs.pop(response_id, None)
            self._persist_unlocked()

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
            self._persist_unlocked()
        for tracked in items:
            await self._terminate(tracked.proc, force=force)

    def reclaim_stale_pids(self) -> int:
        """On startup, SIGTERM any PIDs we previously recorded that still exist."""
        if not self.state_path.exists():
            return 0
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        pids = data.get("pids") if isinstance(data, dict) else None
        if not isinstance(pids, list):
            return 0
        killed = 0
        for entry in pids:
            try:
                pid = int(entry.get("pid") if isinstance(entry, dict) else entry)
            except (TypeError, ValueError):
                continue
            if pid <= 0:
                continue
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError, OSError):
                continue
            try:
                # Prefer process group if we recorded pgid
                pgid = None
                if isinstance(entry, dict):
                    pgid = entry.get("pgid") or entry.get("pid")
                if pgid and os.name != "nt":
                    try:
                        os.killpg(int(pgid), signal.SIGTERM)
                    except (ProcessLookupError, PermissionError, OSError):
                        os.kill(pid, signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)
                killed += 1
                logger.warning("reclaimed stale child pid=%s", pid)
            except (ProcessLookupError, PermissionError, OSError):
                continue
        # Clear stale file after reclaim attempt
        try:
            self.state_path.write_text(
                json.dumps({"pids": [], "updated_at": time.time()}),
                encoding="utf-8",
            )
        except OSError:
            pass
        return killed

    def _persist_unlocked(self) -> None:
        rows = []
        for rid, tracked in self._procs.items():
            proc = tracked.proc
            if proc.returncode is not None or not proc.pid:
                continue
            rows.append(
                {
                    "response_id": rid,
                    "pid": proc.pid,
                    "pgid": proc.pid,
                    "meta": tracked.metadata,
                }
            )
        try:
            self.state_path.write_text(
                json.dumps({"pids": rows, "updated_at": time.time()}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            logger.exception("failed to persist child pid state")

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
