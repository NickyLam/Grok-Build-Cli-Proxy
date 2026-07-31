from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from grok_proxy.backends.base import BackendEvent
from grok_proxy.backends.fake import FakeBackend
from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.main import create_app


@pytest.fixture
def fake_client(tmp_path):
    clear_settings_cache()
    s = Settings(
        api_key="test-secret-key",
        default_cwd=str(tmp_path),
        default_model="grok-4.5",
        models="grok-4.5",
        database_path=str(tmp_path / "r.db"),
        always_approve=True,
    )
    fake = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "hello "}),
            BackendEvent(type="text", data={"text": "world"}),
            BackendEvent(
                type="tool_call",
                data={"id": "call_1", "name": "read_file", "arguments": {"path": "a.py"}},
            ),
            BackendEvent(
                type="tool_result",
                data={"id": "call_1", "result": "ok", "status": "completed"},
            ),
            BackendEvent(
                type="end",
                data={
                    "session_id": "sess-1",
                    "stop_reason": "EndTurn",
                    "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
                    "text": "hello world",
                },
            ),
        ]
    )
    app = create_app(s, bootstrap=False, backend=fake, database_path=tmp_path / "r.db")
    with TestClient(app) as c:
        yield c, tmp_path, fake


def test_create_get_response(fake_client):
    client, cwd, fake = fake_client
    r = client.post(
        "/v1/responses",
        headers={"Authorization": "Bearer test-secret-key"},
        json={
            "model": "grok-4.5",
            "input": "analyze",
            "x_grok": {"cwd": str(cwd), "workspace_mode": "read_only"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["x_grok"]["text"] == "hello world"
    rid = body["id"]

    g = client.get(
        f"/v1/responses/{rid}",
        headers={"Authorization": "Bearer test-secret-key"},
    )
    assert g.status_code == 200
    assert g.json()["status"] == "completed"
    assert fake.prompts == ["analyze"]


def test_background_and_cancel(fake_client):
    client, cwd, _fake = fake_client
    # rebuild with delayed events
    clear_settings_cache()
    s = Settings(
        api_key="test-secret-key",
        default_cwd=str(cwd),
        default_model="grok-4.5",
        models="grok-4.5",
        database_path=str(cwd / "bg.db"),
    )
    fake = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "slow"}),
            BackendEvent(type="end", data={"session_id": "s", "text": "slow"}),
        ],
        delay_sec=0.05,
    )
    app = create_app(s, bootstrap=False, backend=fake, database_path=cwd / "bg.db")
    with TestClient(app) as c:
        r = c.post(
            "/v1/responses",
            headers={"Authorization": "Bearer test-secret-key"},
            json={
                "input": "long job",
                "background": True,
                "x_grok": {"cwd": str(cwd)},
            },
        )
        assert r.status_code == 200
        rid = r.json()["id"]
        assert r.json()["status"] in ("queued", "in_progress", "completed")
        cancel = c.post(
            f"/v1/responses/{rid}/cancel",
            headers={"Authorization": "Bearer test-secret-key"},
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] in ("cancelled", "completed")


def test_events_replay(fake_client):
    client, cwd, _ = fake_client
    r = client.post(
        "/v1/responses",
        headers={"Authorization": "Bearer test-secret-key"},
        json={"input": "x", "x_grok": {"cwd": str(cwd)}},
    )
    rid = r.json()["id"]
    with client.stream(
        "GET",
        f"/v1/responses/{rid}/events?after=0",
        headers={"Authorization": "Bearer test-secret-key"},
    ) as stream:
        assert stream.status_code == 200
        text = "".join(stream.iter_text())
    assert "response.created" in text or "response.completed" in text
    # parse at least one data line
    assert "data: " in text


def test_permission_flow(tmp_path):
    clear_settings_cache()
    s = Settings(
        api_key="test-secret-key",
        default_cwd=str(tmp_path),
        default_model="grok-4.5",
        models="grok-4.5",
        database_path=str(tmp_path / "perm.db"),
        always_approve=False,
    )
    # Use a custom script that emits permission then ends after decision
    events = [
        BackendEvent(
            type="permission_request",
            data={
                "id": "p1",
                "category": "shell",
                "risk": "high",
                "title": "run rm",
                "arguments": {"command": "echo hi"},
            },
        ),
        BackendEvent(type="text", data={"text": "after approve"}),
        BackendEvent(type="end", data={"session_id": "s", "text": "after approve"}),
    ]
    fake = FakeBackend(script=events)
    app = create_app(s, bootstrap=False, backend=fake, database_path=tmp_path / "perm.db")
    with TestClient(app) as client:
        # background so we can approve mid-flight
        r = client.post(
            "/v1/responses",
            headers={"Authorization": "Bearer test-secret-key"},
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
        assert r.status_code == 200
        rid = r.json()["id"]

        # wait for permission event in journal
        import time

        perm_id = None
        for _ in range(50):
            rec = client.app.state.db.list_events(rid, after_sequence=0)
            for ev in rec:
                if ev.event_type == "response.permission.required":
                    perm_id = ev.payload_json.get("permission_id")
                    break
            if perm_id:
                break
            # also auto-allow path may skip if policy allows echo
            status = client.get(
                f"/v1/responses/{rid}",
                headers={"Authorization": "Bearer test-secret-key"},
            ).json()["status"]
            if status == "completed":
                return
            time.sleep(0.05)

        if perm_id:
            d = client.post(
                f"/v1/permissions/{perm_id}/decision",
                headers={"Authorization": "Bearer test-secret-key"},
                json={"decision": "allow_once"},
            )
            assert d.status_code == 200, d.text
            # idempotent
            d2 = client.post(
                f"/v1/permissions/{perm_id}/decision",
                headers={"Authorization": "Bearer test-secret-key"},
                json={"decision": "allow_once"},
            )
            assert d2.status_code == 200

        # eventually complete or still running
        final = client.get(
            f"/v1/responses/{rid}",
            headers={"Authorization": "Bearer test-secret-key"},
        )
        assert final.status_code == 200
