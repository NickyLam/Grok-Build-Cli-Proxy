from __future__ import annotations

from grok_proxy.models import ChatCompletionRequest


def test_x_grok_wins_over_top_level():
    body = ChatCompletionRequest(
        messages=[{"role": "user", "content": "hi"}],
        cwd="/tmp/a",
        session_id="old",
        x_grok={"cwd": "/tmp/b", "session_id": "new", "always_approve": False, "max_turns": 3},
    )
    assert body.cwd == "/tmp/b"
    assert body.session_id == "new"
    assert body.always_approve is False
    assert body.max_turns == 3
