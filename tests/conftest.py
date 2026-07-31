from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from grok_proxy.backends.fake import FakeBackend
from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
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
        backend="headless",
        database_path=str(tmp_path / "test.db"),
        allow_in_place=False,
        default_workspace_mode="read_only",
    )


@pytest.fixture
def app(settings: Settings, tmp_path: Path):
    return create_app(
        settings,
        bootstrap=False,
        database_path=tmp_path / "app.db",
    )


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-secret-key"}


@pytest.fixture
def fake_backend_app(settings: Settings, tmp_path: Path):
    """App wired with FakeBackend for orchestrator / responses tests."""
    fake = FakeBackend()
    application = create_app(
        settings,
        bootstrap=False,
        backend=fake,
        database_path=tmp_path / "fake.db",
    )
    with TestClient(application) as c:
        yield c, fake, tmp_path
