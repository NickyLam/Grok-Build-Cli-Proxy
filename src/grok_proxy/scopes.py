from __future__ import annotations

from enum import StrEnum


class Scope(StrEnum):
    RESPONSE_CREATE = "response:create"
    RESPONSE_READ = "response:read"
    RESPONSE_CANCEL = "response:cancel"
    EVENT_READ = "event:read"
    PERMISSION_READ = "permission:read"
    PERMISSION_APPROVE = "permission:approve"
    WORKSPACE_READ = "workspace:read"
    WORKSPACE_WRITE = "workspace:write"
    TOOL_EXECUTE = "tool:execute"
    ADMIN_KEYS = "admin:keys"


# Master bootstrap key effectively has all scopes.
ALL_SCOPES: frozenset[str] = frozenset(s.value for s in Scope)

# Conservative default for delegated agent keys (no self-approval, no admin).
DEFAULT_AGENT_SCOPES: frozenset[str] = frozenset(
    {
        Scope.RESPONSE_CREATE.value,
        Scope.RESPONSE_READ.value,
        Scope.RESPONSE_CANCEL.value,
        Scope.EVENT_READ.value,
        Scope.PERMISSION_READ.value,
        Scope.WORKSPACE_READ.value,
        Scope.TOOL_EXECUTE.value,
    }
)

# Approver-only key can decide permissions but not necessarily create tasks.
DEFAULT_APPROVER_SCOPES: frozenset[str] = frozenset(
    {
        Scope.RESPONSE_READ.value,
        Scope.EVENT_READ.value,
        Scope.PERMISSION_READ.value,
        Scope.PERMISSION_APPROVE.value,
    }
)


ROUTE_SCOPES: dict[str, set[str]] = {
    "POST /v1/responses": {Scope.RESPONSE_CREATE.value},
    "GET /v1/responses": {Scope.RESPONSE_READ.value},
    "POST /v1/responses/cancel": {Scope.RESPONSE_CANCEL.value},
    "GET /v1/responses/events": {Scope.EVENT_READ.value},
    "GET /v1/permissions": {Scope.PERMISSION_READ.value},
    "POST /v1/permissions/decision": {Scope.PERMISSION_APPROVE.value},
    "POST /v1/chat/completions": {Scope.RESPONSE_CREATE.value},
    "GET /v1/models": set(),  # any authenticated
    "GET /v1/health": set(),
    "GET /v1/connection": set(),
    "GET /v1/keys": {Scope.ADMIN_KEYS.value},
    "POST /v1/keys": {Scope.ADMIN_KEYS.value},
    "DELETE /v1/keys": {Scope.ADMIN_KEYS.value},
    "POST /v1/keys/revoke": {Scope.ADMIN_KEYS.value},
}


def has_scope(granted: set[str] | frozenset[str], required: str | set[str] | frozenset[str]) -> bool:
    if not required:
        return True
    need = {required} if isinstance(required, str) else set(required)
    return need.issubset(set(granted))
