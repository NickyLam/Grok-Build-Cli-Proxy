#!/usr/bin/env python3
"""Probe local `grok agent stdio` ACP handshake (no long coding task).

Usage:
  uv run python scripts/probe_acp.py
  GROK_BIN=/path/to/grok uv run python scripts/probe_acp.py --prompt "Say hi"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys


async def probe(grok_bin: str, cwd: str, prompt: str | None, timeout: float) -> int:
    proc = await asyncio.create_subprocess_exec(
        grok_bin,
        "agent",
        "stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        limit=16 * 1024 * 1024,
    )
    assert proc.stdin and proc.stdout
    proc.stdout._limit = 16 * 1024 * 1024  # type: ignore[attr-defined]
    rid = 0

    async def rpc(method: str, params: dict, to: float = 30.0):
        nonlocal rid
        rid += 1
        my = rid
        msg = {"jsonrpc": "2.0", "id": my, "method": method, "params": params}
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        await proc.stdin.drain()
        print(f">> {method}")
        deadline = asyncio.get_event_loop().time() + to
        while asyncio.get_event_loop().time() < deadline:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=2)
            except TimeoutError:
                continue
            if not line:
                break
            s = line.decode(errors="replace").strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                continue
            if obj.get("id") == my:
                if "error" in obj:
                    print(f"<< ERROR {obj['error']}")
                    return None
                print(f"<< OK {json.dumps(obj.get('result'))[:400]}")
                return obj.get("result")
            m = obj.get("method")
            if m:
                print(f"<< note {m}")
        print(f"<< TIMEOUT {method}")
        return None

    try:
        init = await rpc(
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {"name": "grok-proxy-probe", "version": "0.2.0"},
                "capabilities": {},
            },
            to=15,
        )
        if not init:
            return 2
        print("protocolVersion=", init.get("protocolVersion"))
        print("agentVersion=", (init.get("_meta") or {}).get("agentVersion"))

        await rpc("authenticate", {"methodId": "cached_token"}, to=10)

        sess = await rpc("session/new", {"cwd": cwd, "mcpServers": []}, to=60)
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
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=3)
        except Exception:
            proc.kill()


def main() -> None:
    p = argparse.ArgumentParser(description="Probe grok agent stdio ACP")
    p.add_argument("--grok-bin", default=os.environ.get("GROK_BIN", "grok"))
    p.add_argument("--cwd", default=os.getcwd())
    p.add_argument("--prompt", default=None, help="Optional short prompt")
    p.add_argument("--timeout", type=float, default=120.0)
    args = p.parse_args()
    code = asyncio.run(probe(args.grok_bin, args.cwd, args.prompt, args.timeout))
    sys.exit(code)


if __name__ == "__main__":
    main()
