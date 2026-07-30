from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.grok_runner import GrokResult
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
    )
    app = create_app(s, bootstrap=False)

    async def fake_run(opts):
        return GrokResult(
            text="done",
            session_id="session-xyz",
            stop_reason="EndTurn",
            num_turns=1,
            usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            exit_code=0,
        )

    async def fake_stream(opts):
        yield {"type": "text", "data": "hel"}
        yield {"type": "text", "data": "lo"}
        yield {
            "type": "end",
            "sessionId": "session-stream",
            "stopReason": "EndTurn",
            "num_turns": 1,
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        }

    with TestClient(app) as client:
        client.app.state.runner.run = AsyncMock(side_effect=fake_run)
        client.app.state.runner.stream = fake_stream
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
    assert body["choices"][0]["message"]["content"] == "done"
    assert body["grok"]["session_id"] == "session-xyz"
    assert body["usage"]["total_tokens"] == 3


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
    assert "hel" in text and "lo" in text


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
    # Mock runner accepts any model; ensure response model field is remapped
    assert r.json()["model"] == "grok-4.5"
    # And runner was invoked with remapped id
    call_opts = client.app.state.runner.run.await_args.args[0]
    assert call_opts.model == "grok-4.5"
