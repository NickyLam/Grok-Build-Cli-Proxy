"""Chat completions via orchestrator journal → OpenAI SSE (FakeBackend)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from grok_proxy.backends.base import BackendEvent
from grok_proxy.backends.fake import FakeBackend
from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.main import create_app


@pytest.fixture
def chat_client(tmp_path):
    clear_settings_cache()
    s = Settings(
        api_key="test-secret-key",
        default_cwd=str(tmp_path),
        default_model="grok-4.5",
        models="grok-4.5",
        database_path=str(tmp_path / "chat_stream.db"),
        always_approve=True,
    )
    fake = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "hel"}),
            BackendEvent(type="text", data={"text": "lo"}),
            BackendEvent(
                type="end",
                data={
                    "session_id": "sess-stream-1",
                    "stop_reason": "EndTurn",
                    "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                    "text": "hello",
                },
            ),
        ]
    )
    app = create_app(
        s, bootstrap=False, backend=fake, database_path=tmp_path / "chat_stream.db"
    )
    with TestClient(app) as c:
        yield c, tmp_path, fake


def test_chat_non_stream_returns_response_id(chat_client):
    client, cwd, fake = chat_client
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
    assert body["grok"]["response_id"]
    assert body["grok"]["session_id"] == "sess-stream-1"
    assert fake.prompts


def test_chat_stream_sse_content_from_fake_backend(chat_client):
    client, cwd, fake = chat_client
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
    assert "chat.completion.chunk" in text
    assert fake.prompts

    # Parse content deltas
    contents: list[str] = []
    response_ids: list[str] = []
    for line in text.splitlines():
        if not line.startswith("data: ") or line.strip() == "data: [DONE]":
            continue
        payload = json.loads(line[len("data: ") :])
        delta = (payload.get("choices") or [{}])[0].get("delta") or {}
        if delta.get("content"):
            contents.append(delta["content"])
        grok = payload.get("grok") or {}
        if grok.get("response_id"):
            response_ids.append(grok["response_id"])
    assert "".join(contents) == "hello"
    assert response_ids, "finish chunk should include response_id"
