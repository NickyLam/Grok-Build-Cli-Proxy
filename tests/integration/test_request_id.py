from __future__ import annotations

from fastapi.testclient import TestClient

from grok_proxy.backends.fake import FakeBackend
from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.main import create_app


def test_request_id_header_echo(tmp_path):
    clear_settings_cache()
    s = Settings(
        api_key="k",
        default_cwd=str(tmp_path),
        default_model="m",
        models="m",
        database_path=str(tmp_path / "r.db"),
    )
    app = create_app(s, bootstrap=False, backend=FakeBackend(), database_path=tmp_path / "r.db")
    with TestClient(app) as client:
        r = client.get("/health", headers={"X-Request-ID": "req_custom_123"})
        assert r.status_code == 200
        assert r.headers.get("X-Request-ID") == "req_custom_123"

        r2 = client.get("/health")
        assert r2.headers.get("X-Request-ID", "").startswith("req_")
