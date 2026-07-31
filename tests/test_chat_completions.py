from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from grok_proxy.backends.base import BackendEvent
from grok_proxy.backends.fake import FakeBackend
from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.main import create_app


@pytest.fixture
def mock_runner_app(tmp_path):
    clear_settings_cache()
    s = Settings(
        api_key="test-secret-key",
        default_cwd=str(tmp_path),
        default_model="grok-4.5",
        models="grok-4.5",
        max_concurrent=2,
        grok_bin="grok",
        always_approve=True,
        strict_session_cwd=True,
        database_path=str(tmp_path / "chat.db"),
    )
    # Chat (stream + non-stream) goes through FakeBackend orchestrator path.
    fake = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "hel"}),
            BackendEvent(type="text", data={"text": "lo"}),
            BackendEvent(
                type="end",
                data={
                    "session_id": "session-xyz",
                    "stop_reason": "EndTurn",
                    "num_turns": 1,
                    "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                    "text": "hello",
                },
            ),
        ]
    )
    app = create_app(s, bootstrap=False, backend=fake, database_path=tmp_path / "chat.db")

    with TestClient(app) as client:
        client.app.state._fake = fake  # type: ignore[attr-defined]
        yield client, tmp_path


def test_chat_non_stream(mock_runner_app):
    client, cwd = mock_runner_app
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-secret-key"},
        json={
            "model": "grok-4.5",
            "messages": [{"role": "user", "content": "hi"}],
            "cwd": str(cwd),
            "stream": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["choices"][0]["message"]["content"] == "hello"
    assert body["grok"]["session_id"] == "session-xyz"
    assert body["usage"]["total_tokens"] == 3
    assert body["grok"]["response_id"]


def test_chat_stream(mock_runner_app):
    client, cwd = mock_runner_app
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-secret-key"},
        json={
            "model": "grok-4.5",
            "messages": [{"role": "user", "content": "hi"}],
            "cwd": str(cwd),
            "stream": True,
        },
    ) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())
    assert "data: " in text
    assert "[DONE]" in text
    # Stream via Orchestrator journal → OpenAI SSE
    assert "hel" in text and "lo" in text
    assert "response_id" in text


def test_resume_session_cwd_mismatch(mock_runner_app):
    client, cwd = mock_runner_app
    r1 = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-secret-key"},
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "cwd": str(cwd),
        },
    )
    assert r1.status_code == 200
    sid = r1.json()["grok"]["session_id"]

    other = cwd / "other"
    other.mkdir()
    r2 = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-secret-key"},
        json={
            "messages": [{"role": "user", "content": "again"}],
            "cwd": str(other),
            "session_id": sid,
        },
    )
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "session_cwd_mismatch"


def test_invalid_cwd(mock_runner_app):
    client, cwd = mock_runner_app
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-secret-key"},
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "cwd": str(cwd / "does-not-exist"),
        },
    )
    assert r.status_code == 400


def test_alias_grok_build_remapped(mock_runner_app):
    """WorkBuddy may still send model=grok-build; map to real CLI id."""
    client, cwd = mock_runner_app
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-secret-key"},
        json={
            "model": "grok-build",
            "messages": [{"role": "user", "content": "hi"}],
            "cwd": str(cwd),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["model"] == "grok-4.5"
    fake: FakeBackend = client.app.state._fake  # type: ignore[attr-defined]
    assert fake.started
    assert fake.started[-1].model == "grok-4.5"
