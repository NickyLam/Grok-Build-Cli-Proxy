# Codex / agent MCP integration

The proxy exposes tools over **MCP-style JSON-RPC on stdio**:

```bash
uv run grok-proxy --mcp-stdio
```

This is a **lightweight stdio protocol** implemented by the gateway (tools/list + tools/call).  
If your client requires the full official MCP SDK feature set, verify with the smoke script first.

## Tools

| Tool | Default policy | Purpose |
|------|----------------|---------|
| `grok_consult` | read_only | Architecture / analysis |
| `grok_review` | read_only | Code review |
| `grok_delegate` | worktree + ask | Full coding task |
| `grok_status` | — | Poll response |
| `grok_cancel` | — | Cancel |
| `grok_get_diff` | — | Worktree diff |
| `grok_resume` | — | Continue session |

## Codex config sketch

Exact Codex config keys evolve; use the pattern below and adapt to your Codex version.

**Option A — spawn as MCP server process**

```toml
# Example shape for ~/.codex/config.toml or project config
[mcp_servers.grok_proxy]
command = "uv"
args = ["run", "--directory", "/absolute/path/to/Grok-Build-Cli-Proxy", "grok-proxy", "--mcp-stdio"]
# env if needed:
# env = { GROK_BIN = "/Users/you/.grok/bin/grok", GROK_PROXY_BACKEND = "headless" }
```

**Option B — shell wrapper**

```bash
#!/usr/bin/env bash
# scripts/mcp-grok-proxy.sh
set -euo pipefail
cd /absolute/path/to/Grok-Build-Cli-Proxy
exec uv run grok-proxy --mcp-stdio
```

Then point Codex at that script as the MCP command.

## Manual protocol smoke (no Codex UI)

```bash
# list tools
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | uv run grok-proxy --mcp-stdio

# consult (uses real Grok if authenticated — may cost tokens)
printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"grok_consult","arguments":{"prompt":"Reply with pong only","cwd":"'"$PWD"'"}}}' \
  | uv run grok-proxy --mcp-stdio
```

Or use the script:

```bash
./scripts/e2e_mcp.sh
E2E_LIVE_PROMPT=1 ./scripts/e2e_mcp.sh   # optional live consult
```

## Recommended scopes for Codex

Create a scoped key for agent use (HTTP still uses Bearer; MCP currently shares the process identity of the gateway):

```bash
export KEY="$(cat ~/.grok-proxy/api_key)"
curl -s http://127.0.0.1:8787/v1/keys \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "codex",
    "workspace_allowlist": ["'"$HOME"'/projects"],
    "max_concurrent": 1,
    "max_runtime_sec": 1800,
    "test": true
  }'
```

Do **not** grant `permission:approve` to the agent key. Approve high-risk actions with a separate human token via HTTP:

```bash
curl -s "http://127.0.0.1:8787/v1/permissions?status=pending" \
  -H "Authorization: Bearer $HUMAN_KEY"
```

## Qoder / CodeBuddy

Same MCP stdio command:

```text
command: uv
args: run --directory <repo> grok-proxy --mcp-stdio
```

| Client | Notes |
|--------|--------|
| Qoder | Register as external MCP server; prefer `grok_review` / `grok_consult` first |
| CodeBuddy | Same; long tasks use `grok_delegate` then `grok_status` |

## Troubleshooting

| Issue | Check |
|-------|--------|
| Process exits immediately | Run `uv run grok-proxy --mcp-stdio` and send `tools/list` line |
| Empty tool list | Ensure method name is `tools/list` or `list_tools` |
| Grok not found | `which grok` / `GROK_BIN` |
| Hang on delegate | Permission wait / long task — poll with `grok_status` or use HTTP events |
| Protocol mismatch | Official MCP SDK clients may need full SDK; use e2e_mcp.sh to confirm lite protocol |

## Relation to HTTP

MCP and HTTP share the same **ResponseOrchestrator** and SQLite journal when using the same database path (`GROK_PROXY_DATABASE_PATH` / default `~/.grok-proxy/gateway.db`).
