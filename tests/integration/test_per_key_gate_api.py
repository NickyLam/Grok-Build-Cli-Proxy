from __future__ import annotations

from fastapi.testclient import TestClient

from grok_proxy.backends.base import BackendEvent
from grok_proxy.backends.fake import FakeBackend
from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.main import create_app
from grok_proxy.scopes import DEFAULT_AGENT_SCOPES


def test_per_key_max_concurrent_blocks_second(tmp_path):
    clear_settings_cache()
    s = Settings(
        api_key="master-secret-key",
        default_cwd=str(tmp_path),
        default_model="grok-4.5",
        models="grok-4.5",
        max_concurrent=10,
        database_path=str(tmp_path / "pk.db"),
    )
    # Slow backend so two background tasks overlap
    fake = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "slow"}),
            BackendEvent(type="end", data={"text": "slow"}),
        ],
        delay_sec=0.15,
    )
    app = create_app(s, bootstrap=False, backend=fake, database_path=tmp_path / "pk.db")
    with TestClient(app) as client:
        kr = client.post(
            "/v1/keys",
            headers={"Authorization": "Bearer master-secret-key"},
            json={
                "name": "limited",
                "scopes": list(DEFAULT_AGENT_SCOPES),
                "max_concurrent": 1,
                "workspace_allowlist": [str(tmp_path)],
                "test": True,
            },
        )
        assert kr.status_code == 201, kr.text
        raw = kr.json()["api_key"]

        r1 = client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {raw}"},
            json={
                "input": "job1",
                "background": True,
                "x_grok": {"cwd": str(tmp_path)},
            },
        )
        assert r1.status_code == 200, r1.text
        id1 = r1.json()["id"]

        r2 = client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {raw}"},
            json={
                "input": "job2",
                "background": True,
                "x_grok": {"cwd": str(tmp_path)},
            },
        )
        assert r2.status_code == 200, r2.text
        id2 = r2.json()["id"]

        # Wait for both to settle
        import time

        for _ in range(40):
            s1 = client.get(
                f"/v1/responses/{id1}",
                headers={"Authorization": f"Bearer {raw}"},
            ).json()["status"]
            s2 = client.get(
                f"/v1/responses/{id2}",
                headers={"Authorization": f"Bearer {raw}"},
            ).json()["status"]
            if s1 in ("completed", "failed", "cancelled") and s2 in (
                "completed",
                "failed",
                "cancelled",
            ):
                break
            time.sleep(0.05)

        final1 = client.get(
            f"/v1/responses/{id1}",
            headers={"Authorization": f"Bearer {raw}"},
        ).json()
        final2 = client.get(
            f"/v1/responses/{id2}",
            headers={"Authorization": f"Bearer {raw}"},
        ).json()
        statuses = {final1["status"], final2["status"]}
        # One should complete; the other may fail with key_max_concurrent
        assert "completed" in statuses or final1["status"] == "completed"
        if "failed" in statuses:
            failed = final1 if final1["status"] == "failed" else final2
            assert failed["error"]["code"] == "key_max_concurrent"
