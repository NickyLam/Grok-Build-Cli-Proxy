from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    clear_settings_cache()
    return Settings(
        api_key="test-secret-key",
        host="127.0.0.1",
        port=8787,
        grok_bin="grok",
        default_cwd=str(tmp_path),
        cwd_allowlist=[],
        max_concurrent=2,
        default_timeout_sec=30,
        default_model="grok-4.5",
        always_approve=True,
        strict_session_cwd=True,
        models="grok-4.5",
    )


@pytest.fixture
def app(settings: Settings):
    # settings already has a fixed api_key; skip home-dir bootstrap side effects
    return create_app(settings, bootstrap=False)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-secret-key"}
