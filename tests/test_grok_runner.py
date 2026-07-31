from __future__ import annotations

import asyncio

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


# ---- iter_ndjson_lines: regression for LimitOverrunError on huge tool results ----


def _reader_with(data: bytes) -> asyncio.StreamReader:
    # Small internal limit to mirror asyncio's 64 KiB default behaviour;
    # iter_ndjson_lines must be immune to it because it uses read(), not readline().
    reader = asyncio.StreamReader(limit=2**16)
    reader.feed_data(data)
    reader.feed_eof()
    return reader


async def test_iter_ndjson_lines_handles_line_over_64k():
    """A single >64 KiB NDJSON line (e.g. web-search tool result) must survive."""
    import json

    from grok_proxy.grok_runner import iter_ndjson_lines

    big = json.dumps({"type": "tool_result", "result": "X" * 100_000}).encode()
    data = b'{"type": "text", "text": "a"}\n' + big + b'\n{"type": "end"}\n'
    lines = [line async for line in iter_ndjson_lines(_reader_with(data))]
    assert len(lines) == 3
    assert json.loads(lines[1])["result"] == "X" * 100_000
    assert json.loads(lines[2]) == {"type": "end"}


async def test_iter_ndjson_lines_drops_pathological_line_and_continues():
    from grok_proxy.grok_runner import iter_ndjson_lines

    huge = b"Y" * 300_000  # above the max_line_bytes cap below
    data = b"first\n" + huge + b"\nlast\n"
    lines = [
        line
        async for line in iter_ndjson_lines(_reader_with(data), max_line_bytes=100_000)
    ]
    assert lines == [b"first", b"last"]


async def test_iter_ndjson_lines_yields_trailing_line_without_newline():
    from grok_proxy.grok_runner import iter_ndjson_lines

    lines = [line async for line in iter_ndjson_lines(_reader_with(b"a\nb"))]
    assert lines == [b"a", b"b"]
