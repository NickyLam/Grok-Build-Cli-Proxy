#!/usr/bin/env python3
"""Probe local `grok agent stdio` ACP handshake (no long coding task).

Usage:
  uv run python scripts/probe_acp.py
  GROK_BIN=/path/to/grok uv run python scripts/probe_acp.py --prompt "Say hi"

Common failure: TIMEOUT initialize
  - grok agent cold-start is slow (plugins / MCP)
  - stderr pipe fills if not drained (process stalls)
  - initialize JSON line is very large (need big StreamReader limit)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

STREAM_LIMIT = 32 * 1024 * 1024


async def probe(
    grok_bin: str,
    cwd: str,
    prompt: str | None,
    timeout: float,
    *,
    init_timeout: float,
    verbose: bool,
) -> int:
    env = os.environ.copy()
    # Prefer a quieter probe when supported; ignore if CLI ignores these.
    env.setdefault("GROK_DISABLE_AUTOUPDATER", "1")

    proc = await asyncio.create_subprocess_exec(
        grok_bin,
        "agent",
        "stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    assert proc.stdin and proc.stdout and proc.stderr
    try:
        proc.stdout._limit = STREAM_LIMIT  # type: ignore[attr-defined]
        proc.stderr._limit = STREAM_LIMIT  # type: ignore[attr-defined]
    except Exception:
        pass

    stderr_chunks: list[bytes] = []

    async def drain_stderr() -> None:
        assert proc.stderr is not None
        try:
            while True:
                chunk = await proc.stderr.read(8192)
                if not chunk:
                    break
                stderr_chunks.append(chunk)
                if verbose:
                    sys.stderr.write(chunk.decode(errors="replace"))
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"[stderr drain] {e}", file=sys.stderr)

    stderr_task = asyncio.create_task(drain_stderr())
    rid = 0

    def stderr_tail(n: int = 1500) -> str:
        return b"".join(stderr_chunks).decode(errors="replace")[-n:]

    async def read_line(timeout_s: float) -> bytes | None:
        """Read one NDJSON line; tolerate oversize lines."""
        assert proc.stdout is not None
        try:
            return await asyncio.wait_for(proc.stdout.readline(), timeout=timeout_s)
        except TimeoutError:
            return None
        except ValueError as e:
            # Separator found but chunk longer than limit
            print(f"<< ValueError reading stdout: {e}", file=sys.stderr)
            # Best-effort: try to enlarge and continue
            try:
                proc.stdout._limit = STREAM_LIMIT * 2  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                return await asyncio.wait_for(proc.stdout.readline(), timeout=timeout_s)
            except Exception:
                return None

    async def rpc(method: str, params: dict, to: float = 30.0) -> dict | None:
        nonlocal rid
        rid += 1
        my = rid
        msg = {"jsonrpc": "2.0", "id": my, "method": method, "params": params}
        raw = (json.dumps(msg, ensure_ascii=False) + "\n").encode()
        proc.stdin.write(raw)
        await proc.stdin.drain()
        print(f">> {method}")
        t0 = time.monotonic()
        deadline = t0 + to
        notes = 0
        while time.monotonic() < deadline:
            remaining = max(0.1, deadline - time.monotonic())
            line = await read_line(min(3.0, remaining))
            if line is None:
                # no data this slice; keep waiting until overall deadline
                if proc.returncode is not None:
                    print(f"<< process exited code={proc.returncode}")
                    tail = stderr_tail()
                    if tail:
                        print("<< stderr tail:\n" + tail)
                    return None
                continue
            if not line:
                print("<< EOF on stdout")
                tail = stderr_tail()
                if tail:
                    print("<< stderr tail:\n" + tail)
                return None
            s = line.decode(errors="replace").strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                if verbose:
                    print(f"<< non-json ({len(s)} chars): {s[:120]!r}")
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("id") == my:
                if "error" in obj:
                    print(f"<< ERROR {obj['error']}")
                    return None
                print(f"<< OK {json.dumps(obj.get('result'), ensure_ascii=False)[:400]}")
                if verbose:
                    print(f"   ({time.monotonic() - t0:.1f}s, notes={notes})")
                return obj.get("result") if isinstance(obj.get("result"), dict) else {}
            m = obj.get("method")
            if m:
                notes += 1
                print(f"<< note {m}")
        print(f"<< TIMEOUT {method} after {to:.0f}s")
        tail = stderr_tail()
        if tail:
            print("<< stderr tail:\n" + tail)
        else:
            print("<< stderr empty (if process hung, try again; cold start can be slow)")
        if proc.returncode is not None:
            print(f"<< process already exited: {proc.returncode}")
        return None

    try:
        # Give binary a moment to open stdio before first write (helps some cold starts)
        await asyncio.sleep(0.15)

        init = await rpc(
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {"name": "grok-proxy-probe", "version": "0.2.0"},
                "capabilities": {},
            },
            to=init_timeout,
        )
        if not init:
            return 2
        print("protocolVersion=", init.get("protocolVersion"))
        meta = init.get("_meta") if isinstance(init.get("_meta"), dict) else {}
        print("agentVersion=", meta.get("agentVersion"))

        auth = await rpc("authenticate", {"methodId": "cached_token"}, to=max(15.0, init_timeout / 2))
        if auth is None:
            print("WARN authenticate failed/timeout — continuing (session/new may still work)")

        sess = await rpc(
            "session/new",
            {"cwd": cwd, "mcpServers": []},
            to=max(60.0, init_timeout),
        )
        if not sess or not sess.get("sessionId"):
            print("session/new failed")
            return 3
        sid = sess["sessionId"]
        print("sessionId=", sid)

        if prompt:
            result = await rpc(
                "session/prompt",
                {
                    "sessionId": sid,
                    "prompt": [{"type": "text", "text": prompt}],
                },
                to=timeout,
            )
            if not result:
                return 4
            print("stopReason=", result.get("stopReason"))
            meta = result.get("_meta") or {}
            usage = meta.get("usage") or {}
            print(
                "usage tokens=",
                usage.get("totalTokens") or usage.get("total_tokens"),
            )
        print("PROBE OK")
        return 0
    finally:
        stderr_task.cancel()
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass
        try:
            if proc.returncode is None:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def main() -> None:
    p = argparse.ArgumentParser(description="Probe grok agent stdio ACP")
    p.add_argument("--grok-bin", default=os.environ.get("GROK_BIN", "grok"))
    p.add_argument("--cwd", default=os.getcwd())
    p.add_argument("--prompt", default=None, help="Optional short prompt")
    p.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("E2E_ACP_PROMPT_TIMEOUT", "120")),
        help="Timeout for optional session/prompt",
    )
    p.add_argument(
        "--init-timeout",
        type=float,
        default=float(os.environ.get("E2E_ACP_INIT_TIMEOUT", "60")),
        help="Timeout for initialize/authenticate (cold start can exceed 15s)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    code = asyncio.run(
        probe(
            args.grok_bin,
            args.cwd,
            args.prompt,
            args.timeout,
            init_timeout=args.init_timeout,
            verbose=args.verbose,
        )
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
