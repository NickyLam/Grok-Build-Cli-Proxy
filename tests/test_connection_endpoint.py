from __future__ import annotations


def test_connection_requires_auth(client):
    r = client.get("/v1/connection")
    assert r.status_code == 401


def test_connection_returns_fields(client, auth_headers):
    r = client.get("/v1/connection", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["base_url"] == "http://127.0.0.1:8787/v1"
    assert body["api_key"] == "test-secret-key"
    assert body["model_id"] == "grok-4.5"
    assert body["workbuddy"]["url"] == body["base_url"]
    assert body["workbuddy"]["apiKey"] == "test-secret-key"
    assert body["openai_sdk"]["model"] == "grok-4.5"
