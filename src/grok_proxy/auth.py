from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.security.utils import get_authorization_scheme_param

from grok_proxy.api_keys import AuthContext
from grok_proxy.config import Settings
from grok_proxy.errors import ProxyError
from grok_proxy.scopes import ALL_SCOPES

if TYPE_CHECKING:
    from grok_proxy.api_keys import ApiKeyStore


def extract_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if not auth:
        alt = request.headers.get("x-api-key") or request.headers.get("api-key")
        return alt.strip() if alt else None
    scheme, param = get_authorization_scheme_param(auth)
    if scheme.lower() != "bearer" or not param:
        return None
    return param


def master_auth_context(settings: Settings) -> AuthContext:
    return AuthContext(
        actor_type="master",
        actor_id="master",
        scopes=ALL_SCOPES,
        workspace_allowlist=[],
        is_master=True,
        key_name="master",
    )


def verify_request_auth(request: Request, settings: Settings) -> None:
    """Backward-compatible check (master key only). Prefer authenticate_request."""
    ctx = authenticate_request(request, settings)
    request.state.auth = ctx


def authenticate_request(
    request: Request,
    settings: Settings,
    *,
    key_store: ApiKeyStore | None = None,
) -> AuthContext:
    expected = settings.api_key
    if not expected:
        raise ProxyError(
            "Server misconfigured: GROK_PROXY_API_KEY is empty",
            status_code=503,
            code="missing_server_api_key",
        )
    token = extract_bearer_token(request)
    if token is None:
        raise ProxyError(
            "Invalid or missing API key. Use Authorization: Bearer <key>.",
            status_code=401,
            code="invalid_api_key",
        )

    # Master bootstrap key (plaintext compare, constant-time)
    if secrets.compare_digest(token, expected):
        ctx = master_auth_context(settings)
        request.state.auth = ctx
        return ctx

    # Scoped keys (hash lookup)
    store = key_store
    if store is None:
        store = getattr(request.app.state, "key_store", None)
    if store is not None:
        rec = store.authenticate(token)
        if rec is not None:
            ctx = AuthContext(
                actor_type="api_key",
                actor_id=rec.id,
                scopes=frozenset(rec.scopes),
                workspace_allowlist=list(rec.workspace_allowlist),
                max_concurrent=rec.max_concurrent,
                max_runtime_sec=rec.max_runtime_sec,
                workspace_mode=rec.workspace_mode,
                key_id=rec.id,
                key_name=rec.name,
                is_master=False,
            )
            request.state.auth = ctx
            return ctx

    raise ProxyError(
        "Invalid or missing API key. Use Authorization: Bearer <GROK_PROXY_API_KEY>.",
        status_code=401,
        code="invalid_api_key",
    )


def get_auth_context(request: Request) -> AuthContext:
    ctx = getattr(request.state, "auth", None)
    if isinstance(ctx, AuthContext):
        return ctx
    raise ProxyError("Unauthenticated", status_code=401, code="invalid_api_key")
