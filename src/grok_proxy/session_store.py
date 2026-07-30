from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SessionRecord:
    session_id: str
    cwd: str


class SessionStore:
    """In-memory map of Grok session_id → last cwd for strict resume checks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, SessionRecord] = {}

    def remember(self, session_id: str, cwd: str) -> None:
        if not session_id:
            return
        resolved = str(Path(cwd).expanduser().resolve(strict=False))
        with self._lock:
            self._by_id[session_id] = SessionRecord(session_id=session_id, cwd=resolved)

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            return self._by_id.get(session_id)

    def check_cwd(self, session_id: str, cwd: str, *, strict: bool) -> None:
        from grok_proxy.errors import ProxyError

        if not strict:
            return
        rec = self.get(session_id)
        if rec is None:
            # Unknown to proxy (e.g. session from raw CLI) — allow, Grok will validate
            return
        resolved = str(Path(cwd).expanduser().resolve(strict=False))
        if resolved != rec.cwd:
            raise ProxyError(
                f"session_id was created with cwd={rec.cwd!r}, but request cwd={resolved!r}. "
                "Use the same working_directory/cwd when resuming, or set "
                "GROK_PROXY_STRICT_SESSION_CWD=false.",
                status_code=400,
                code="session_cwd_mismatch",
            )
