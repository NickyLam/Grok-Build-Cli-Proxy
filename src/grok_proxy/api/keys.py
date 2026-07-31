from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from grok_proxy.api_keys import ApiKeyStore
from grok_proxy.auth import get_auth_context
from grok_proxy.scopes import Scope


class CreateKeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    scopes: list[str] | None = None
    workspace_allowlist: list[str] | None = None
    max_concurrent: int | None = None
    max_runtime_sec: int | None = None
    workspace_mode: str | None = None
    test: bool = False


def build_keys_router(*, require_auth: Any) -> APIRouter:
    router = APIRouter(prefix="/v1/keys", tags=["keys"])

    def _store(request: Request) -> ApiKeyStore:
        return request.app.state.key_store

    @router.get("")
    async def list_keys(request: Request, _: None = Depends(require_auth)):
        get_auth_context(request).require_scopes(Scope.ADMIN_KEYS.value)
        store = _store(request)
        return JSONResponse(
            content={"object": "list", "data": [store.public_view(k) for k in store.list_keys()]}
        )

    @router.post("")
    async def create_key(
        body: CreateKeyBody,
        request: Request,
        _: None = Depends(require_auth),
    ):
        get_auth_context(request).require_scopes(Scope.ADMIN_KEYS.value)
        store = _store(request)
        rec = store.create(
            name=body.name,
            scopes=body.scopes,
            workspace_allowlist=body.workspace_allowlist,
            max_concurrent=body.max_concurrent,
            max_runtime_sec=body.max_runtime_sec,
            workspace_mode=body.workspace_mode,
            test=body.test,
        )
        view = store.public_view(rec)
        # plaintext only once
        view["api_key"] = rec.plaintext_once
        view["warning"] = "Store api_key now; it will not be shown again."
        return JSONResponse(content=view, status_code=201)

    @router.get("/{key_id}")
    async def get_key(key_id: str, request: Request, _: None = Depends(require_auth)):
        get_auth_context(request).require_scopes(Scope.ADMIN_KEYS.value)
        store = _store(request)
        return JSONResponse(content=store.public_view(store.get(key_id)))

    @router.post("/{key_id}/revoke")
    async def revoke_key(key_id: str, request: Request, _: None = Depends(require_auth)):
        get_auth_context(request).require_scopes(Scope.ADMIN_KEYS.value)
        store = _store(request)
        rec = store.revoke(key_id)
        return JSONResponse(content=store.public_view(rec))

    @router.post("/{key_id}/enable")
    async def enable_key(key_id: str, request: Request, _: None = Depends(require_auth)):
        get_auth_context(request).require_scopes(Scope.ADMIN_KEYS.value)
        store = _store(request)
        rec = store.set_enabled(key_id, True)
        return JSONResponse(content=store.public_view(rec))

    @router.post("/{key_id}/disable")
    async def disable_key(key_id: str, request: Request, _: None = Depends(require_auth)):
        get_auth_context(request).require_scopes(Scope.ADMIN_KEYS.value)
        store = _store(request)
        rec = store.set_enabled(key_id, False)
        return JSONResponse(content=store.public_view(rec))

    return router
