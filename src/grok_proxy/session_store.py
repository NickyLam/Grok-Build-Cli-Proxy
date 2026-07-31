from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grok_proxy.storage.database import Database


@dataclass
class SessionRecord:
    session_id: str
    cwd: str


class SessionStore:
    """Map of Grok session_id → last cwd for strict resume checks.

    Backed by the SQLite `sessions` table when a Database is provided, so the
    strict_session_cwd check survives proxy restarts. An in-memory cache keeps
    the hot path cheap.
    """

    def __init__(self, db: Database | None = None) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, SessionRecord] = {}
        self._db = db

    def remember(self, session_id: str, cwd: str) -> None:
        if not session_id:
            return
        resolved = str(Path(cwd).expanduser().resolve(strict=False))
        with self._lock:
            self._by_id[session_id] = SessionRecord(session_id=session_id, cwd=resolved)
        if self._db is not None:
            self._db.upsert_session(session_id, source_cwd=resolved)

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            rec = self._by_id.get(session_id)
        if rec is not None:
            return rec
        if self._db is not None:
            row = self._db.get_session(session_id)
            if row is not None and row.get("source_cwd"):
                rec = SessionRecord(session_id=session_id, cwd=str(row["source_cwd"]))
                with self._lock:
                    self._by_id[session_id] = rec
                return rec
        return None

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
