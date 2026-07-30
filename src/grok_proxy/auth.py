from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.security.utils import get_authorization_scheme_param

from grok_proxy.config import Settings
from grok_proxy.errors import ProxyError


def extract_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if not auth:
        # OpenAI SDK also sends api_key as Authorization; some clients use x-api-key
        alt = request.headers.get("x-api-key") or request.headers.get("api-key")
        return alt.strip() if alt else None
    scheme, param = get_authorization_scheme_param(auth)
    if scheme.lower() != "bearer" or not param:
        return None
    return param


def verify_request_auth(request: Request, settings: Settings) -> None:
    expected = settings.api_key
    if not expected:
        raise ProxyError(
            "Server misconfigured: GROK_PROXY_API_KEY is empty",
            status_code=503,
            code="missing_server_api_key",
        )
    token = extract_bearer_token(request)
    if token is None or not secrets.compare_digest(token, expected):
        raise ProxyError(
            "Invalid or missing API key. Use Authorization: Bearer <GROK_PROXY_API_KEY>.",
            status_code=401,
            code="invalid_api_key",
        )
