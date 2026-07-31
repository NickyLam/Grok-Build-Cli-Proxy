from __future__ import annotations

from fastapi.testclient import TestClient

from grok_proxy.backends.fake import FakeBackend
from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.main import create_app


def test_metrics_endpoint(tmp_path):
    clear_settings_cache()
    s = Settings(
        api_key="k",
        default_cwd=str(tmp_path),
        default_model="m",
        models="m",
        database_path=str(tmp_path / "m.db"),
    )
    app = create_app(s, bootstrap=False, backend=FakeBackend(), database_path=tmp_path / "m.db")
    with TestClient(app) as client:
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "grok_proxy_uptime_seconds" in r.text
