from __future__ import annotations

from fastapi.testclient import TestClient

from grok_proxy.backends.base import BackendEvent
from grok_proxy.backends.fake import FakeBackend
from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.main import create_app
from grok_proxy.scopes import DEFAULT_AGENT_SCOPES, Scope


def _app(tmp_path, *, fake: FakeBackend | None = None):
    clear_settings_cache()
    s = Settings(
        api_key="master-secret-key",
        default_cwd=str(tmp_path),
        default_model="grok-4.5",
        models="grok-4.5",
        database_path=str(tmp_path / "keys.db"),
    )
    backend = fake or FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "ok"}),
            BackendEvent(type="end", data={"text": "ok", "session_id": "s"}),
        ]
    )
    return create_app(s, bootstrap=False, backend=backend, database_path=tmp_path / "keys.db")


def test_create_scoped_key_and_use(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        # Master creates a key
        r = client.post(
            "/v1/keys",
            headers={"Authorization": "Bearer master-secret-key"},
            json={
                "name": "agent-a",
                "scopes": list(DEFAULT_AGENT_SCOPES),
                "workspace_allowlist": [str(tmp_path)],
                "test": True,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        raw = body["api_key"]
        assert raw.startswith("gp_test_")
        key_id = body["id"]

        # Scoped key can create response
        r2 = client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {raw}"},
            json={"input": "hi", "x_grok": {"cwd": str(tmp_path)}},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "completed"

        # Scoped key cannot approve (no scope)
        r3 = client.post(
            "/v1/permissions/perm_fake/decision",
            headers={"Authorization": f"Bearer {raw}"},
            json={"decision": "allow_once"},
        )
        assert r3.status_code == 403
        assert r3.json()["error"]["code"] == "insufficient_scope"

        # Scoped key cannot list keys
        r4 = client.get(
            "/v1/keys",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert r4.status_code == 403

        # Outside allowlist: sibling path not under key allowlist
        other = tmp_path.parent / "not-allowed-workspace"
        other.mkdir(exist_ok=True)
        r5 = client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {raw}"},
            json={"input": "hi", "x_grok": {"cwd": str(other)}},
        )
        assert r5.status_code == 403
        assert r5.json()["error"]["code"] in ("key_cwd_forbidden", "cwd_forbidden")

        # Revoke
        rev = client.post(
            f"/v1/keys/{key_id}/revoke",
            headers={"Authorization": "Bearer master-secret-key"},
        )
        assert rev.status_code == 200
        r6 = client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {raw}"},
            json={"input": "hi", "x_grok": {"cwd": str(tmp_path)}},
        )
        assert r6.status_code == 401


def test_approver_key_cannot_create(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/v1/keys",
            headers={"Authorization": "Bearer master-secret-key"},
            json={
                "name": "approver",
                "scopes": [
                    Scope.PERMISSION_APPROVE.value,
                    Scope.PERMISSION_READ.value,
                    Scope.RESPONSE_READ.value,
                ],
                "test": True,
            },
        )
        raw = r.json()["api_key"]
        r2 = client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {raw}"},
            json={"input": "x", "x_grok": {"cwd": str(tmp_path)}},
        )
        assert r2.status_code == 403
