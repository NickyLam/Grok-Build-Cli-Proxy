from __future__ import annotations

from grok_proxy.grok_runner import GrokRunOptions, build_grok_argv, map_usage, parse_json_result


def test_build_argv_basic():
    opts = GrokRunOptions(
        prompt="hi",
        model="grok-build",
        cwd="/tmp/x",
        stream=False,
        always_approve=True,
        max_turns=5,
        session_id="sess-1",
        grok_bin="grok",
    )
    cmd = build_grok_argv(opts)
    assert cmd[0] == "grok"
    assert "-p" in cmd and "hi" in cmd
    assert "--resume" in cmd and "sess-1" in cmd
    assert "--max-turns" in cmd and "5" in cmd
    assert "--always-approve" in cmd
    assert "--output-format" in cmd and "json" in cmd


def test_build_argv_prompt_file():
    opts = GrokRunOptions(
        prompt="",
        model="m",
        cwd="/tmp",
        prompt_file="/secret/prompt.txt",
    )
    cmd = build_grok_argv(opts)
    assert "--prompt-file" in cmd
    assert "/secret/prompt.txt" in cmd
    assert "hi" not in cmd
    assert "-p" not in cmd


def test_build_argv_stream():
    opts = GrokRunOptions(prompt="x", model="m", cwd="/tmp", stream=True)
    cmd = build_grok_argv(opts)
    assert "streaming-json" in cmd


def test_parse_json_result():
    r = parse_json_result(
        {
            "text": "hello",
            "sessionId": "abc",
            "stopReason": "EndTurn",
            "num_turns": 2,
            "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
        },
        exit_code=0,
    )
    assert r.text == "hello"
    assert r.session_id == "abc"
    assert r.num_turns == 2
    pt, ct, tt = map_usage(r.usage)
    assert (pt, ct, tt) == (10, 3, 13)


def test_map_usage_empty():
    assert map_usage(None) == (0, 0, 0)
