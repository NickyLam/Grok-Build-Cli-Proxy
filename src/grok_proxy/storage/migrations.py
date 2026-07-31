from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS responses (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        model TEXT NOT NULL,
        backend TEXT NOT NULL,
        input_json TEXT NOT NULL,
        output_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        x_grok_json TEXT NOT NULL DEFAULT '{}',
        session_id TEXT,
        source_cwd TEXT,
        run_cwd TEXT,
        workspace_mode TEXT,
        created_at REAL NOT NULL,
        started_at REAL,
        completed_at REAL,
        cancelled_at REAL,
        last_sequence_number INTEGER NOT NULL DEFAULT 0,
        error_code TEXT,
        error_message TEXT,
        usage_json TEXT,
        text TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        backend TEXT NOT NULL,
        backend_session_id TEXT,
        source_cwd TEXT,
        run_cwd TEXT,
        model TEXT,
        status TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        last_response_id TEXT
    );

    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        response_id TEXT NOT NULL,
        sequence_number INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        UNIQUE(response_id, sequence_number),
        FOREIGN KEY(response_id) REFERENCES responses(id)
    );

    CREATE INDEX IF NOT EXISTS idx_events_response_seq
        ON events(response_id, sequence_number);

    CREATE TABLE IF NOT EXISTS tool_calls (
        id TEXT PRIMARY KEY,
        response_id TEXT NOT NULL,
        backend_tool_call_id TEXT,
        tool_type TEXT,
        tool_name TEXT,
        status TEXT,
        arguments_json TEXT,
        result_json TEXT,
        started_at REAL,
        completed_at REAL,
        FOREIGN KEY(response_id) REFERENCES responses(id)
    );

    CREATE TABLE IF NOT EXISTS permissions (
        id TEXT PRIMARY KEY,
        response_id TEXT NOT NULL,
        tool_call_id TEXT,
        status TEXT NOT NULL,
        category TEXT NOT NULL,
        risk TEXT NOT NULL,
        arguments_json TEXT NOT NULL,
        options_json TEXT NOT NULL,
        decision TEXT,
        decision_scope_json TEXT,
        feedback TEXT,
        requested_at REAL NOT NULL,
        decided_at REAL,
        expires_at REAL,
        decided_by TEXT,
        title TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        FOREIGN KEY(response_id) REFERENCES responses(id)
    );

    CREATE TABLE IF NOT EXISTS workspace_locks (
        workspace_key TEXT PRIMARY KEY,
        lock_type TEXT NOT NULL,
        response_id TEXT,
        owner_id TEXT,
        acquired_at REAL,
        expires_at REAL
    );

    CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY,
        key_hash TEXT NOT NULL UNIQUE,
        name TEXT,
        scopes_json TEXT NOT NULL DEFAULT '[]',
        workspace_allowlist_json TEXT NOT NULL DEFAULT '[]',
        max_concurrent INTEGER,
        max_runtime_sec INTEGER,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at REAL NOT NULL,
        last_used_at REAL
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        actor_type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        action TEXT NOT NULL,
        resource_type TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at REAL NOT NULL
    );
    """,
    2: """
    -- Scoped API key extensions
    ALTER TABLE api_keys ADD COLUMN workspace_mode TEXT;
    ALTER TABLE api_keys ADD COLUMN revoked_at REAL;
    """,
}


def apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at REAL NOT NULL
        )
        """
    )
    current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
    import time

    for version in sorted(MIGRATIONS):
        if version <= current:
            continue
        conn.executescript(MIGRATIONS[version])
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, time.time()),
        )
    conn.commit()
