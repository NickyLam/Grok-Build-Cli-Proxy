# Version Compatibility Matrix

| Component | Supported | Notes |
|-----------|-----------|-------|
| Python | 3.11, 3.12, 3.13 | `requires-python >= 3.11` |
| Grok Build CLI | current `grok` on PATH | Headless: `grok -p`; ACP: `grok agent` (stdio) |
| OpenAI Python SDK | 1.x (Responses + Chat) | Base URL `http://127.0.0.1:8787/v1` |
| WorkBuddy custom model | OpenAI-compatible Chat Completions | See `~/.grok-proxy/workbuddy-model.json` |
| FastAPI | ≥ 0.115 | ASGI app |
| Pydantic | v2 | Settings + request models |

## API surface by proxy version

| Proxy | Chat Completions | Responses | Permissions | MCP |
|-------|------------------|-----------|-------------|-----|
| 0.1.x | yes (headless) | no | no | no |
| 0.2.x | yes (via orchestrator) | yes | yes (basic) | yes (stdio tools) |

## Backend selection

| `GROK_PROXY_BACKEND` | Meaning |
|----------------------|---------|
| `headless` (default in 0.2 until ACP is verified) | `grok -p --prompt-file` |
| `acp` | `grok agent` JSON-RPC stdio |
| `auto` | Prefer ACP when binary supports it, else headless |
