from __future__ import annotations

import time
from typing import Any

from grok_proxy.errors import ProxyError
from grok_proxy.permissions.policy import PolicyEngine, PolicyEvaluation
from grok_proxy.storage.database import Database, new_id
from grok_proxy.storage.models import PermissionRecord

DEFAULT_PERMISSION_OPTIONS = [
    {"id": "allow_once", "label": "Allow once"},
    {"id": "allow_for_session", "label": "Allow for session"},
    {"id": "deny_once", "label": "Deny"},
    {"id": "deny_with_feedback", "label": "Deny with feedback"},
    {"id": "cancel_run", "label": "Cancel task"},
]


class PermissionBroker:
    def __init__(
        self,
        db: Database,
        policy: PolicyEngine | None = None,
        *,
        permission_timeout_sec: float = 900,
    ) -> None:
        self.db = db
        self.policy = policy or PolicyEngine()
        self.permission_timeout_sec = permission_timeout_sec

    def evaluate(
        self,
        *,
        category: str,
        risk: str = "medium",
        arguments: dict[str, Any] | None = None,
        force_ask: bool = False,
    ) -> PolicyEvaluation:
        return self.policy.evaluate(
            category=category,
            risk=risk,
            arguments=arguments,
            force_ask=force_ask,
        )

    def create_pending(
        self,
        *,
        response_id: str,
        category: str,
        risk: str,
        arguments: dict[str, Any],
        tool_call_id: str | None = None,
        title: str = "",
        description: str = "",
    ) -> PermissionRecord:
        now = time.time()
        record = PermissionRecord(
            id=new_id("perm"),
            response_id=response_id,
            tool_call_id=tool_call_id,
            status="pending",
            category=category,
            risk=risk,
            arguments_json=arguments,
            options_json=list(DEFAULT_PERMISSION_OPTIONS),
            requested_at=now,
            expires_at=now + self.permission_timeout_sec,
            title=title,
            description=description,
        )
        self.db.create_permission(record)
        self.db.insert_audit(
            actor_type="system",
            actor_id="permission_broker",
            action="permission.created",
            resource_type="permission",
            resource_id=record.id,
            payload={"response_id": response_id, "category": category, "risk": risk},
        )
        return record

    def get(self, permission_id: str) -> PermissionRecord:
        rec = self.db.get_permission(permission_id)
        if rec is None:
            raise ProxyError("permission not found", status_code=404, code="permission_not_found")
        return rec

    def decide(
        self,
        permission_id: str,
        *,
        decision: str,
        actor_id: str = "api",
        feedback: str | None = None,
        scope: dict[str, Any] | None = None,
    ) -> PermissionRecord:
        rec = self.get(permission_id)
        # Idempotent: same decision is OK
        if rec.status != "pending":
            if rec.decision == decision:
                return rec
            raise ProxyError(
                f"permission already decided: {rec.decision}",
                status_code=409,
                code="permission_already_decided",
            )
        now = time.time()
        if rec.expires_at is not None and now > rec.expires_at:
            rec.status = "expired"
            rec.decision = "expired"
            rec.decided_at = now
            self.db.update_permission(rec)
            raise ProxyError("permission expired", status_code=410, code="permission_expired")

        allowed = {
            "allow_once",
            "allow_for_session",
            "deny_once",
            "deny_with_feedback",
            "cancel_run",
        }
        if decision not in allowed:
            raise ProxyError(
                f"invalid decision: {decision}",
                status_code=400,
                code="invalid_decision",
            )

        rec.status = "decided"
        rec.decision = decision
        rec.feedback = feedback
        rec.decision_scope_json = scope
        rec.decided_at = now
        rec.decided_by = actor_id
        self.db.update_permission(rec)
        self.db.insert_audit(
            actor_type="user",
            actor_id=actor_id,
            action="permission.decided",
            resource_type="permission",
            resource_id=rec.id,
            payload={"decision": decision, "feedback": feedback, "scope": scope},
        )
        return rec
