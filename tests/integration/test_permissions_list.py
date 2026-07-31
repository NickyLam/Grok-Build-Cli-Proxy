"""GET /v1/permissions?status=pending after a permission-request FakeBackend run."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from grok_proxy.backends.base import BackendEvent
from grok_proxy.backends.fake import FakeBackend
from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.main import create_app


def test_list_pending_permissions(tmp_path):
    clear_settings_cache()
    s = Settings(
        api_key="test-secret-key",
        default_cwd=str(tmp_path),
        default_model="grok-4.5",
        models="grok-4.5",
        database_path=str(tmp_path / "perm_list.db"),
        always_approve=False,
    )
    events = [
        BackendEvent(
            type="permission_request",
            data={
                "id": "p1",
                "category": "shell",
                "risk": "high",
                "title": "run dangerous",
                "arguments": {"command": "rm -rf nowhere"},
            },
        ),
        BackendEvent(type="text", data={"text": "after"}),
        BackendEvent(type="end", data={"session_id": "s", "text": "after"}),
    ]
    fake = FakeBackend(script=events)
    app = create_app(
        s, bootstrap=False, backend=fake, database_path=tmp_path / "perm_list.db"
    )
    headers = {"Authorization": "Bearer test-secret-key"}

    with TestClient(app) as client:
        r = client.post(
            "/v1/responses",
            headers=headers,
            json={
                "input": "do shell",
                "background": True,
                "x_grok": {
                    "cwd": str(tmp_path),
                    "permission_policy": "ask",
                    "always_approve": False,
                },
            },
        )
        assert r.status_code == 200, r.text
        rid = r.json()["id"]

        pending = []
        for _ in range(50):
            listed = client.get(
                "/v1/permissions?status=pending",
                headers=headers,
            )
            assert listed.status_code == 200, listed.text
            body = listed.json()
            assert body["object"] == "list"
            pending = body["data"]
            if pending:
                break
            # Policy may auto-allow some shell patterns; skip if already done
            status = client.get(f"/v1/responses/{rid}", headers=headers).json()["status"]
            if status == "completed":
                break
            time.sleep(0.05)

        assert pending, "expected at least one pending permission"
        assert all(p["status"] == "pending" for p in pending)
        assert any(p["response_id"] == rid for p in pending)
        assert any(p.get("category") == "shell" for p in pending)

        # Filter by response_id
        by_resp = client.get(
            f"/v1/permissions?status=pending&response_id={rid}",
            headers=headers,
        )
        assert by_resp.status_code == 200
        data = by_resp.json()["data"]
        assert data
        assert all(p["response_id"] == rid for p in data)
