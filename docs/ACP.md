# ACP Backend (`grok agent stdio`)

## Enable

```bash
export GROK_PROXY_BACKEND=acp
# or with automatic Headless fallback:
export GROK_PROXY_BACKEND=auto
uv run grok-proxy
```

## Verified protocol (Grok Build CLI 0.2.x)

Transport: **JSON-RPC 2.0 over NDJSON** (one JSON object per line).

| Step | Method | Params (essentials) |
|------|--------|---------------------|
| 1 | `initialize` | `protocolVersion: 1`, `clientInfo`, `capabilities: {}` |
| 2 | `authenticate` | `methodId: "cached_token"` (uses `~/.grok/auth.json`) |
| 3 | `session/new` | `cwd`, **`mcpServers: []`** (required field) |
| 4 | `session/prompt` | `sessionId`, `prompt: [{type:"text", text:"..."}]` |

### Streaming updates

Notification method: `session/update`

```json
{
  "sessionId": "…",
  "update": {
    "sessionUpdate": "agent_message_chunk",
    "content": {"type": "text", "text": "…"}
  }
}
```

Common `sessionUpdate` values:

| Value | Gateway mapping |
|-------|-----------------|
| `agent_message_chunk` | `text` event |
| `agent_thought_chunk` | dropped by default (privacy) |
| tool / plan / permission variants | tool_call / plan / permission_request |

### Prompt result

RPC result:

```json
{
  "stopReason": "end_turn",
  "_meta": {
    "usage": {
      "inputTokens": 1,
      "outputTokens": 1,
      "totalTokens": 2
    }
  }
}
```

## Probe

```bash
uv run python scripts/probe_acp.py
uv run python scripts/probe_acp.py --prompt "Reply with: pong"
# cold start can exceed 15s — default init timeout is 60s
E2E_ACP_INIT_TIMEOUT=90 uv run python scripts/probe_acp.py -v
```

Exit codes: `0` OK, `2` initialize fail, `3` session fail, `4` prompt fail.

### `TIMEOUT initialize` troubleshooting

| Cause | Fix |
|-------|-----|
| Cold start slow (plugins / MCP like Pencil) | Raise `E2E_ACP_INIT_TIMEOUT` (default 60) |
| stderr pipe full (process stuck) | Probe now drains stderr; update to latest `scripts/probe_acp.py` |
| Huge JSON line | StreamReader limit raised to 32MB |
| Auth / network hang | Check `~/.grok/auth.json`, retry; use `-v` for stderr |
| Binary wrong | `which grok` → should be Grok Build CLI with `agent stdio` |

## Cancel

Grok CLI 0.2.x does not expose a stable cancel RPC in our probes. The gateway **terminates the process group** on cancel/timeout.

## Failover

`GROK_PROXY_BACKEND=auto` uses ACP first; on handshake failure falls back to Headless (`grok -p --prompt-file`).

## Auth requirements

- `authenticate` with `cached_token` expects a valid local Grok login (`grok login` / auth.json).
- Without auth, `session/new` may still succeed but prompts can fail.
