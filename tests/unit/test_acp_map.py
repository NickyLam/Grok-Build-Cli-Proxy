from __future__ import annotations

from grok_proxy.backends.acp_map import map_session_update, normalize_usage


def test_map_agent_message_chunk():
    ev = map_session_update(
        {
            "sessionId": "s",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "hi"},
            },
        }
    )
    assert ev is not None
    assert ev.type == "text"
    assert ev.data["text"] == "hi"


def test_drop_thoughts_by_default():
    ev = map_session_update(
        {
            "update": {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "secret"},
            }
        }
    )
    assert ev is None
    ev2 = map_session_update(
        {
            "update": {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "secret"},
            }
        },
        include_thoughts=True,
    )
    assert ev2 is not None
    assert ev2.data.get("thought") is True


def test_normalize_usage():
    u = normalize_usage(
        {
            "inputTokens": 10,
            "outputTokens": 3,
            "totalTokens": 13,
            "cachedReadTokens": 2,
            "reasoningTokens": 1,
        }
    )
    assert u["input_tokens"] == 10
    assert u["output_tokens"] == 3
    assert u["total_tokens"] == 13
    assert u["cached_tokens"] == 2
    assert u["reasoning_tokens"] == 1
