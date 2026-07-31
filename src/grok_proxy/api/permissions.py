from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from grok_proxy.auth import get_auth_context
from grok_proxy.runtime.orchestrator import ResponseOrchestrator
from grok_proxy.scopes import Scope


class PermissionDecisionBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    decision: str
    feedback: str | None = None
    scope: dict[str, Any] | None = None


class BulkDecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permission_ids: list[str] = Field(min_length=1, max_length=100)
    decision: str = "deny_once"
    feedback: str | None = None


def _perm_json(rec: Any) -> dict[str, Any]:
    return {
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
        "tool_call_id": rec.tool_call_id,
    }


def build_permissions_router(*, require_auth: Any) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["permissions"])

    def _orch(request: Request) -> ResponseOrchestrator:
        return request.app.state.orchestrator

    @router.get("/permissions")
    async def list_permissions(
        request: Request,
        _: None = Depends(require_auth),
        status: str | None = "pending",
        response_id: str | None = None,
        limit: int = 100,
    ):
        get_auth_context(request).require_scopes(Scope.PERMISSION_READ.value)
        rows = _orch(request).permissions.list(
            status=status if status not in ("", "all", "*") else None,
            response_id=response_id,
            limit=limit,
        )
        return JSONResponse(
            content={"object": "list", "data": [_perm_json(r) for r in rows]}
        )

    @router.get("/permissions/{permission_id}")
    async def get_permission(
        permission_id: str,
        request: Request,
        _: None = Depends(require_auth),
    ):
        get_auth_context(request).require_scopes(Scope.PERMISSION_READ.value)
        rec = _orch(request).permissions.get(permission_id)
        return JSONResponse(content=_perm_json(rec))

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

    @router.post("/permissions/bulk_decision")
    async def bulk_decision(
        body: BulkDecisionBody,
        request: Request,
        _: None = Depends(require_auth),
    ):
        auth = get_auth_context(request)
        auth.require_scopes(Scope.PERMISSION_APPROVE.value)
        orch = _orch(request)
        # Prefer orchestrator path for cancel_run side effects when possible
        decided = []
        for pid in body.permission_ids:
            try:
                rec = await orch.decide_permission(
                    pid,
                    decision=body.decision,
                    actor_id=auth.actor_id,
                    feedback=body.feedback,
                )
                decided.append(
                    {
                        "id": rec.id,
                        "response_id": rec.response_id,
                        "status": rec.status,
                        "decision": rec.decision,
                    }
                )
            except Exception as e:  # noqa: BLE001
                decided.append({"id": pid, "error": str(e)})
        return JSONResponse(content={"object": "list", "data": decided})

    return router
