# Grok Build CLI Proxy

OpenAI-compatible HTTP API that wraps the **Grok Build CLI** headless mode (`grok -p`) so other agents can call Grok as a full coding agent.

```
Other agents  ──OpenAI HTTP──▶  grok-proxy  ──spawn──▶  grok -p --always-approve …
```

## Features (v0.1)

- `POST /v1/chat/completions` (JSON + SSE stream)
- `GET /v1/models`
- Request-level **`cwd`** / **`working_directory`**
- Optional **`session_id`** → `grok --resume` (multi-turn)
- Local bind `127.0.0.1` + **Bearer** auth
- Concurrency limit, timeouts, optional cwd allowlist

## Requirements

- Python 3.11+
- [Grok Build CLI](https://x.ai) installed and authenticated (`XAI_API_KEY` or `grok login`)
- `grok` on `PATH` (or set `GROK_BIN`)

## Install

```bash
cd Grok-Build-Cli-Proxy
uv sync --all-extras   # or: pip install -e ".[dev]"
# optional: cp .env.example .env
```

## Run

```bash
# API Key is auto-generated on first start (saved under ~/.grok-proxy/)
# optional: export XAI_API_KEY='xai-...'   # only if not using `grok login` subscription
uv run grok-proxy

# One-shot: also write WorkBuddy Custom model entry
uv run grok-proxy --install-workbuddy

# Only generate key + config files, do not listen
uv run grok-proxy --print-config-only --install-workbuddy
```

On startup the tool prints **Base URL / API Key / Model ID** and writes:

| File | Purpose |
|------|---------|
| `~/.grok-proxy/api_key` | Persisted proxy Bearer token |
| `~/.grok-proxy/client-config.json` | Generic OpenAI-compatible fields |
| `~/.grok-proxy/workbuddy-model.json` | Single WorkBuddy `models.json` entry |
| `~/.grok-proxy/credentials.json` | Full connection snapshot |

Or:

```bash
uv run python -m grok_proxy
uv run uvicorn grok_proxy.main:app --host 127.0.0.1 --port 8787
```

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | no | Liveness + in-flight count |
| GET | `/v1/health` | yes | Same, authenticated |
| GET | `/v1/connection` | yes | `base_url` / `api_key` / `model_id` + WorkBuddy 片段 |
| GET | `/v1/models` | yes | Model list |
| POST | `/v1/chat/completions` | yes | Run coding agent |

### Extensions on `chat/completions`

| Field | Maps to |
|-------|---------|
| `cwd` / `working_directory` | `--cwd` |
| `session_id` | `--resume` |
| `max_turns` | `--max-turns` |
| `sandbox` | `--sandbox` |
| `rules` | `--rules` |
| `yolo` / `always_approve` | `--always-approve` (default true) |
| `tools_allow` / `tools_deny` | `--tools` / `--disallowed-tools` |
| `allow` / `deny` | `--allow` / `--deny` |
| `reasoning_effort` | `--effort` |
| `worktree` | `--worktree` |
| `timeout_sec` | proxy kill timeout |
| `include_thoughts` | stream thinking into content (optional) |

Response includes a **`grok`** object:

```json
{
  "grok": {
    "session_id": "…",
    "stop_reason": "EndTurn",
    "num_turns": 3,
    "request_id": "…",
    "raw_usage": {}
  }
}
```

Use `grok.session_id` on the next request to continue the same Grok session (same `cwd`).

### curl

```bash
export KEY=your-long-secret

curl -s http://127.0.0.1:8787/v1/chat/completions \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-build",
    "messages": [{"role":"user","content":"List top-level files and summarize the project."}],
    "cwd": "/path/to/repo",
    "stream": false
  }' | jq .
```

### OpenAI Python SDK

```python
from openai import OpenAI
import json
from pathlib import Path

cfg = json.loads(Path.home().joinpath(".grok-proxy/client-config.json").read_text())
client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
r = client.chat.completions.create(
    model=cfg["model"],
    messages=[{"role": "user", "content": "Fix the failing unit tests."}],
    extra_body={"cwd": "/path/to/repo", "max_turns": 30},
)
print(r.choices[0].message.content)
```

### WorkBuddy (Custom model)

```bash
uv run grok-proxy --install-workbuddy
```

Or paste `~/.grok-proxy/workbuddy-model.json` into `~/.workbuddy/models.json`:

- **url** → Base URL  
- **apiKey** → API Key（启动时自动生成，`sk-gp-…`）  
- **id** → Model ID（**必须是本机 `grok models` 里的真实 id**，当前常见为 `grok-4.5`；不要用文档旧名 `grok-build`）

UI：添加 Custom model，填启动横幅里的三项即可。  
也可 `GET /v1/connection`（需 Bearer）拿到同样 JSON。

> 若报 `unknown model id`：说明 WorkBuddy 传的 model 不是 CLI 支持的 id。重启 proxy（会自动探测），并 `--install-workbuddy` 刷新配置。Proxy 也会把 `grok-build` 等别名映射到默认真实模型。

## Security model

This proxy is equivalent to **“anyone with the Bearer token can run a local coding agent with tool access under the allowed cwd prefixes.”**

- Default bind: **127.0.0.1 only**
- **API key auto-generated** on first start (or set `GROK_PROXY_API_KEY`); stored `0600` under `~/.grok-proxy/`
- Optional **`GROK_PROXY_CWD_ALLOWLIST`** restricts workspaces
- Default **`--always-approve`** (no interactive prompts); rely on Grok deny rules / hooks / sandbox for hard limits
- Do **not** expose this service to the public internet without additional controls

## Configuration

See [`.env.example`](.env.example). Common env vars:

| Variable | Default | Meaning |
|----------|---------|---------|
| `GROK_PROXY_API_KEY` | auto `sk-gp-…` | Bearer token (optional override) |
| `GROK_PROXY_HOME` | `~/.grok-proxy` | State dir for key + client configs |
| `GROK_PROXY_INSTALL_WORKBUDDY` | false | Upsert `~/.workbuddy/models.json` on start |
| `GROK_PROXY_HOST` | `127.0.0.1` | Bind host |
| `GROK_PROXY_PORT` | `8787` | Port |
| `GROK_BIN` | `grok` | CLI path |
| `GROK_PROXY_DEFAULT_CWD` | process cwd | Default workspace |
| `GROK_PROXY_CWD_ALLOWLIST` | empty | Allowed path prefixes |
| `GROK_PROXY_MAX_CONCURRENT` | `2` | Parallel runs |
| `GROK_PROXY_DEFAULT_TIMEOUT_SEC` | `600` | Per-request timeout |
| `GROK_PROXY_STRICT_SESSION_CWD` | `true` | Resume must reuse known cwd |

## Session semantics

| Case | Prompt construction |
|------|---------------------|
| No `session_id` | Linearize `messages` (system → `--rules` when leading) |
| With `session_id` | Last message must be `user`; history lives in Grok session |

## Development

```bash
uv sync --all-extras
uv run pytest
```

## Non-goals (v0.1)

- Multi-tenant / cloud SaaS
- ACP WebSocket gateway (use `grok agent serve` directly)
- MCP server surface (possible later)

## License

MIT
