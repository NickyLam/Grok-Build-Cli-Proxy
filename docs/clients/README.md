# Client integration guide

How to connect popular clients to **Grok Build CLI Proxy** (v0.2).

## Prerequisites

```bash
# 1. Grok CLI authenticated
grok login   # or: export XAI_API_KEY=...

# 2. Start the gateway
cd Grok-Build-Cli-Proxy
uv sync --all-extras
uv run grok-proxy
```

On first start the proxy prints **Base URL**, **API Key**, and **Model ID**, and writes:

| File | Use for |
|------|---------|
| `~/.grok-proxy/api_key` | Bearer token |
| `~/.grok-proxy/client-config.json` | OpenAI SDK / generic clients |
| `~/.grok-proxy/workbuddy-model.json` | WorkBuddy custom model |

```bash
export GROK_PROXY_BASE_URL=http://127.0.0.1:8787/v1
export GROK_PROXY_API_KEY="$(cat ~/.grok-proxy/api_key)"
export GROK_PROXY_MODEL="$(python3 -c 'import json;print(json.load(open(__import__("pathlib").Path.home()/".grok-proxy/client-config.json"))["model"])' 2>/dev/null || echo grok-4.5)"
```

## Guides

| Client | Transport | Doc |
|--------|-----------|-----|
| curl / HTTP | OpenAI-compatible REST | [curl.md](./curl.md) |
| OpenAI Python SDK | Chat Completions | [openai-sdk.md](./openai-sdk.md) |
| WorkBuddy | Custom model | [workbuddy.md](./workbuddy.md) |
| Codex (and similar agents) | MCP stdio | [codex-mcp.md](./codex-mcp.md) |
| Qoder / CodeBuddy | MCP stdio (same shape) | [codex-mcp.md](./codex-mcp.md#qoder--codebuddy) |

## Smoke tests (automated)

```bash
# Proxy must already be running for HTTP checks
./scripts/e2e_http.sh

# MCP tools over stdio (starts its own process)
./scripts/e2e_mcp.sh

# Live ACP handshake (requires grok agent stdio)
./scripts/e2e_acp.sh

# All of the above that can run
./scripts/e2e_all.sh
```

Optional live model call (costs tokens):

```bash
E2E_LIVE_PROMPT=1 ./scripts/e2e_http.sh
RUN_GROK_E2E=1 uv run pytest -m grok_e2e -q
```

## Security tips for clients

1. Prefer a **scoped API key** for agents (no `permission:approve`).
2. Set `workspace_allowlist` to the projects the agent may touch.
3. Keep the proxy on `127.0.0.1` unless you fully understand the risk.
4. Headless backend forces tool auto-approve; use `GROK_PROXY_BACKEND=acp` when you need human approval.

See [../SECURITY.md](../SECURITY.md).
