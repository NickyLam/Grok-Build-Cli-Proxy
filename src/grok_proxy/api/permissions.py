from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from grok_proxy.auth import get_auth_context
from grok_proxy.runtime.orchestrator import ResponseOrchestrator
from grok_proxy.scopes import Scope


class PermissionDecisionBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    decision: str
    feedback: str | None = None
    scope: dict[str, Any] | None = None


def build_permissions_router(*, require_auth: Any) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["permissions"])

    def _orch(request: Request) -> ResponseOrchestrator:
        return request.app.state.orchestrator

    @router.get("/permissions/{permission_id}")
    async def get_permission(
        permission_id: str,
        request: Request,
        _: None = Depends(require_auth),
    ):
        get_auth_context(request).require_scopes(Scope.PERMISSION_READ.value)
        rec = _orch(request).permissions.get(permission_id)
        return JSONResponse(
            content={
                "id": rec.id,
                "response_id": rec.response_id,
                "status": rec.status,
                "category": rec.category,
                "risk": rec.risk,
                "arguments": rec.arguments_json,
                "options": rec.options_json,
                "decision": rec.decision,
                "feedback": rec.feedback,
                "title": rec.title,
                "description": rec.description,
                "requested_at": rec.requested_at,
                "expires_at": rec.expires_at,
                "decided_at": rec.decided_at,
                "decided_by": rec.decided_by,
            }
        )

    @router.post("/permissions/{permission_id}/decision")
    async def decide_permission(
        permission_id: str,
        body: PermissionDecisionBody,
        request: Request,
        _: None = Depends(require_auth),
    ):
        auth = get_auth_context(request)
        auth.require_scopes(Scope.PERMISSION_APPROVE.value)
        rec = await _orch(request).decide_permission(
            permission_id,
            decision=body.decision,
            actor_id=auth.actor_id,
            feedback=body.feedback,
            scope=body.scope,
        )
        return JSONResponse(
            content={
                "id": rec.id,
                "response_id": rec.response_id,
                "status": rec.status,
                "decision": rec.decision,
                "feedback": rec.feedback,
                "decided_at": rec.decided_at,
            }
        )

    return router
