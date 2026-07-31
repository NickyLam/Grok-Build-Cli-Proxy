from __future__ import annotations

from grok_proxy.backends.headless import map_streaming_event
from grok_proxy.grok_runner import GrokRunOptions, build_grok_argv


def test_map_text_tool_plan_usage_end():
    assert map_streaming_event({"type": "text", "data": "hi"}).type == "text"
    assert map_streaming_event({"type": "tool_call", "name": "shell", "id": "c1"}).type == "tool_call"
    assert map_streaming_event({"type": "plan", "plan": []}).type == "plan"
    assert map_streaming_event({"type": "usage", "usage": {"input_tokens": 1}}).type == "usage"
    assert map_streaming_event({"type": "end", "sessionId": "s"}).type == "end"
    assert map_streaming_event({"type": "error", "message": "x"}).type == "error"
    assert map_streaming_event({"type": "thought", "data": "secret"}) is None


def test_prompt_file_argv():
    opts = GrokRunOptions(
        prompt="",
        model="m",
        cwd="/tmp",
        prompt_file="/tmp/p.txt",
        always_approve=True,
    )
    cmd = build_grok_argv(opts)
    assert "--prompt-file" in cmd
    assert "/tmp/p.txt" in cmd
    assert "-p" not in cmd
