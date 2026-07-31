from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResponseRecord:
    id: str
    status: str
    model: str
    backend: str
    input_json: dict[str, Any]
    output_json: list[dict[str, Any]] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)
    x_grok_json: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    source_cwd: str | None = None
    run_cwd: str | None = None
    workspace_mode: str | None = None
    created_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    cancelled_at: float | None = None
    last_sequence_number: int = 0
    error_code: str | None = None
    error_message: str | None = None
    usage_json: dict[str, Any] | None = None
    text: str = ""


@dataclass
class EventRecord:
    id: str
    response_id: str
    sequence_number: int
    event_type: str
    payload_json: dict[str, Any]
    created_at: float


@dataclass
class PermissionRecord:
    id: str
    response_id: str
    tool_call_id: str | None
    status: str
    category: str
    risk: str
    arguments_json: dict[str, Any]
    options_json: list[dict[str, Any]]
    decision: str | None = None
    decision_scope_json: dict[str, Any] | None = None
    feedback: str | None = None
    requested_at: float = 0.0
    decided_at: float | None = None
    expires_at: float | None = None
    decided_by: str | None = None
    title: str = ""
    description: str = ""
