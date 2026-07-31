from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from grok_proxy.storage.migrations import apply_migrations
from grok_proxy.storage.models import EventRecord, PermissionRecord, ResponseRecord


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class Database:
    """Thread-safe SQLite store (WAL)."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        apply_migrations(self._conn)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # ---- responses ----

    def create_response(self, record: ResponseRecord) -> ResponseRecord:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO responses (
                    id, status, model, backend, input_json, output_json, metadata_json,
                    x_grok_json, session_id, source_cwd, run_cwd, workspace_mode,
                    created_at, started_at, completed_at, cancelled_at, last_sequence_number,
                    error_code, error_message, usage_json, text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.status,
                    record.model,
                    record.backend,
                    _json_dumps(record.input_json),
                    _json_dumps(record.output_json),
                    _json_dumps(record.metadata_json),
                    _json_dumps(record.x_grok_json),
                    record.session_id,
                    record.source_cwd,
                    record.run_cwd,
                    record.workspace_mode,
                    record.created_at,
                    record.started_at,
                    record.completed_at,
                    record.cancelled_at,
                    record.last_sequence_number,
                    record.error_code,
                    record.error_message,
                    _json_dumps(record.usage_json) if record.usage_json is not None else None,
                    record.text,
                ),
            )
        return record

    def get_response(self, response_id: str) -> ResponseRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM responses WHERE id = ?", (response_id,)
            ).fetchone()
        return self._row_to_response(row) if row else None

    def update_response(self, record: ResponseRecord) -> ResponseRecord:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE responses SET
                    status=?, model=?, backend=?, input_json=?, output_json=?, metadata_json=?,
                    x_grok_json=?, session_id=?, source_cwd=?, run_cwd=?, workspace_mode=?,
                    created_at=?, started_at=?, completed_at=?, cancelled_at=?,
                    last_sequence_number=?, error_code=?, error_message=?, usage_json=?, text=?
                WHERE id=?
                """,
                (
                    record.status,
                    record.model,
                    record.backend,
                    _json_dumps(record.input_json),
                    _json_dumps(record.output_json),
                    _json_dumps(record.metadata_json),
                    _json_dumps(record.x_grok_json),
                    record.session_id,
                    record.source_cwd,
                    record.run_cwd,
                    record.workspace_mode,
                    record.created_at,
                    record.started_at,
                    record.completed_at,
                    record.cancelled_at,
                    record.last_sequence_number,
                    record.error_code,
                    record.error_message,
                    _json_dumps(record.usage_json) if record.usage_json is not None else None,
                    record.text,
                    record.id,
                ),
            )
        return record

    def append_event(
        self,
        response_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        event_id: str | None = None,
        created_at: float | None = None,
    ) -> EventRecord:
        eid = event_id or new_id("evt")
        ts = created_at if created_at is not None else time.time()
        with self.transaction() as conn:
            # Atomic sequence allocation (avoids races under multi-thread TestClient)
            cur = conn.execute(
                """
                UPDATE responses
                SET last_sequence_number = last_sequence_number + 1
                WHERE id = ?
                RETURNING last_sequence_number
                """,
                (response_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"response not found: {response_id}")
            seq = int(row[0] if not isinstance(row, sqlite3.Row) else row["last_sequence_number"])
            try:
                conn.execute(
                    """
                    INSERT INTO events (id, response_id, sequence_number, event_type, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (eid, response_id, seq, event_type, _json_dumps(payload), ts),
                )
            except sqlite3.IntegrityError:
                # Fallback: derive next seq from events table
                max_row = conn.execute(
                    "SELECT COALESCE(MAX(sequence_number), 0) AS m FROM events WHERE response_id = ?",
                    (response_id,),
                ).fetchone()
                seq = int(max_row[0] if not isinstance(max_row, sqlite3.Row) else max_row["m"]) + 1
                conn.execute(
                    """
                    INSERT INTO events (id, response_id, sequence_number, event_type, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (eid, response_id, seq, event_type, _json_dumps(payload), ts),
                )
                conn.execute(
                    "UPDATE responses SET last_sequence_number = ? WHERE id = ?",
                    (seq, response_id),
                )
        return EventRecord(
            id=eid,
            response_id=response_id,
            sequence_number=seq,
            event_type=event_type,
            payload_json=payload,
            created_at=ts,
        )

    def list_events(self, response_id: str, *, after_sequence: int = 0) -> list[EventRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM events
                WHERE response_id = ? AND sequence_number > ?
                ORDER BY sequence_number ASC
                """,
                (response_id, after_sequence),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def create_permission(self, record: PermissionRecord) -> PermissionRecord:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO permissions (
                    id, response_id, tool_call_id, status, category, risk,
                    arguments_json, options_json, decision, decision_scope_json, feedback,
                    requested_at, decided_at, expires_at, decided_by, title, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.response_id,
                    record.tool_call_id,
                    record.status,
                    record.category,
                    record.risk,
                    _json_dumps(record.arguments_json),
                    _json_dumps(record.options_json),
                    record.decision,
                    _json_dumps(record.decision_scope_json)
                    if record.decision_scope_json is not None
                    else None,
                    record.feedback,
                    record.requested_at,
                    record.decided_at,
                    record.expires_at,
                    record.decided_by,
                    record.title,
                    record.description,
                ),
            )
        return record

    def get_permission(self, permission_id: str) -> PermissionRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM permissions WHERE id = ?", (permission_id,)
            ).fetchone()
        return self._row_to_permission(row) if row else None

    def update_permission(self, record: PermissionRecord) -> PermissionRecord:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE permissions SET
                    status=?, decision=?, decision_scope_json=?, feedback=?,
                    decided_at=?, decided_by=?, expires_at=?
                WHERE id=?
                """,
                (
                    record.status,
                    record.decision,
                    _json_dumps(record.decision_scope_json)
                    if record.decision_scope_json is not None
                    else None,
                    record.feedback,
                    record.decided_at,
                    record.decided_by,
                    record.expires_at,
                    record.id,
                ),
            )
        return record

    def list_pending_permissions(self, response_id: str) -> list[PermissionRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM permissions WHERE response_id = ? AND status = 'pending'",
                (response_id,),
            ).fetchall()
        return [self._row_to_permission(r) for r in rows]

    def insert_audit(
        self,
        *,
        actor_type: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (
                    id, actor_type, actor_id, action, resource_type, resource_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("aud"),
                    actor_type,
                    actor_id,
                    action,
                    resource_type,
                    resource_id,
                    _json_dumps(payload or {}),
                    time.time(),
                ),
            )

    # ---- api keys ----

    def create_api_key(self, record: Any) -> Any:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO api_keys (
                    id, key_hash, name, scopes_json, workspace_allowlist_json,
                    max_concurrent, max_runtime_sec, enabled, created_at, last_used_at,
                    workspace_mode, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.key_hash,
                    record.name,
                    _json_dumps(record.scopes),
                    _json_dumps(record.workspace_allowlist),
                    record.max_concurrent,
                    record.max_runtime_sec,
                    1 if record.enabled else 0,
                    record.created_at,
                    record.last_used_at,
                    record.workspace_mode,
                    record.revoked_at,
                ),
            )
        return record

    def get_api_key(self, key_id: str) -> Any | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM api_keys WHERE id = ?", (key_id,)
            ).fetchone()
        return self._row_to_api_key(row) if row else None

    def get_api_key_by_hash(self, key_hash: str) -> Any | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
            ).fetchone()
        return self._row_to_api_key(row) if row else None

    def list_api_keys(self) -> list[Any]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM api_keys ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_api_key(r) for r in rows]

    def update_api_key(self, record: Any) -> Any:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE api_keys SET
                    name=?, scopes_json=?, workspace_allowlist_json=?,
                    max_concurrent=?, max_runtime_sec=?, enabled=?,
                    last_used_at=?, workspace_mode=?, revoked_at=?
                WHERE id=?
                """,
                (
                    record.name,
                    _json_dumps(record.scopes),
                    _json_dumps(record.workspace_allowlist),
                    record.max_concurrent,
                    record.max_runtime_sec,
                    1 if record.enabled else 0,
                    record.last_used_at,
                    record.workspace_mode,
                    record.revoked_at,
                    record.id,
                ),
            )
        return record

    def touch_api_key(self, key_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (time.time(), key_id),
            )

    def count_responses_by_status(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS c FROM responses GROUP BY status"
            ).fetchall()
        return {str(r["status"]): int(r["c"]) for r in rows}

    def count_pending_permissions(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM permissions WHERE status = 'pending'"
            ).fetchone()
        return int(row["c"] if row else 0)

    @staticmethod
    def _row_to_api_key(row: sqlite3.Row) -> Any:
        # Late import to avoid circular deps at module load
        from grok_proxy.api_keys import ApiKeyRecord

        keys = row.keys()
        return ApiKeyRecord(
            id=row["id"],
            key_hash=row["key_hash"],
            name=row["name"] or "",
            scopes=_json_loads(row["scopes_json"], []),
            workspace_allowlist=_json_loads(row["workspace_allowlist_json"], []),
            max_concurrent=row["max_concurrent"],
            max_runtime_sec=row["max_runtime_sec"],
            workspace_mode=row["workspace_mode"] if "workspace_mode" in keys else None,
            enabled=bool(row["enabled"]),
            created_at=float(row["created_at"] or 0),
            last_used_at=float(row["last_used_at"]) if row["last_used_at"] is not None else None,
            revoked_at=(
                float(row["revoked_at"])
                if "revoked_at" in keys and row["revoked_at"] is not None
                else None
            ),
        )

    @staticmethod
    def _row_to_response(row: sqlite3.Row) -> ResponseRecord:
        return ResponseRecord(
            id=row["id"],
            status=row["status"],
            model=row["model"],
            backend=row["backend"],
            input_json=_json_loads(row["input_json"], {}),
            output_json=_json_loads(row["output_json"], []),
            metadata_json=_json_loads(row["metadata_json"], {}),
            x_grok_json=_json_loads(row["x_grok_json"], {}),
            session_id=row["session_id"],
            source_cwd=row["source_cwd"],
            run_cwd=row["run_cwd"],
            workspace_mode=row["workspace_mode"],
            created_at=float(row["created_at"] or 0),
            started_at=float(row["started_at"]) if row["started_at"] is not None else None,
            completed_at=float(row["completed_at"]) if row["completed_at"] is not None else None,
            cancelled_at=float(row["cancelled_at"]) if row["cancelled_at"] is not None else None,
            last_sequence_number=int(row["last_sequence_number"] or 0),
            error_code=row["error_code"],
            error_message=row["error_message"],
            usage_json=_json_loads(row["usage_json"], None),
            text=row["text"] or "",
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> EventRecord:
        return EventRecord(
            id=row["id"],
            response_id=row["response_id"],
            sequence_number=int(row["sequence_number"]),
            event_type=row["event_type"],
            payload_json=_json_loads(row["payload_json"], {}),
            created_at=float(row["created_at"] or 0),
        )

    @staticmethod
    def _row_to_permission(row: sqlite3.Row) -> PermissionRecord:
        return PermissionRecord(
            id=row["id"],
            response_id=row["response_id"],
            tool_call_id=row["tool_call_id"],
            status=row["status"],
            category=row["category"],
            risk=row["risk"],
            arguments_json=_json_loads(row["arguments_json"], {}),
            options_json=_json_loads(row["options_json"], []),
            decision=row["decision"],
            decision_scope_json=_json_loads(row["decision_scope_json"], None),
            feedback=row["feedback"],
            requested_at=float(row["requested_at"] or 0),
            decided_at=float(row["decided_at"]) if row["decided_at"] is not None else None,
            expires_at=float(row["expires_at"]) if row["expires_at"] is not None else None,
            decided_by=row["decided_by"],
            title=row["title"] or "",
            description=row["description"] or "",
        )


def open_database(path: str | Path) -> Database:
    return Database(path)
