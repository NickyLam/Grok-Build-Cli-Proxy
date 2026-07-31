<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="Grok Build CLI Proxy — local OpenAI-compatible Agent Gateway for Grok Build">
</p>

<p align="center">
  <strong>Local Agent Gateway</strong> for <a href="https://x.ai">Grok Build CLI</a><br/>
  OpenAI Chat Completions · Responses API · permissions · workspaces · MCP
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#api-essentials">API</a> ·
  <a href="#agent-clients">Clients</a> ·
  <a href="#security">Security</a> ·
  <a href="docs/clients/README.md">Integration guide</a> ·
  <a href="docs/ACP.md">ACP</a>
</p>

---

## What it is

Other agents and IDEs speak **OpenAI HTTP** or **MCP**. Grok Build speaks **CLI / ACP**.

This proxy is the bridge: a single local process that turns Grok into a **stateful agent gateway** — not just a one-shot chat completion wrapper.

| You call | Gateway does | Grok runs as |
|----------|--------------|--------------|
| `POST /v1/chat/completions` | Orchestrate + stream/JSON | Headless or ACP |
| `POST /v1/responses` | Create / poll / cancel / SSE replay | Same |
| MCP tools | `grok_consult` / `review` / `delegate` … | Same |

**v0.2** keeps WorkBuddy / OpenAI SDK clients working, and adds Responses lifecycle, scoped keys, permissions, and ACP (`grok agent stdio`).

---

## How it works

<p align="center">
  <img src="./assets/readme/architecture.svg" width="100%" alt="API gateway into Response Orchestrator with Headless, ACP, and SQLite journal">
</p>

- **Orchestrator** owns the response state machine, event journal, cancel, timeout, and permission waits.
- **HeadlessBackend** (default): `grok -p --prompt-file` (prompt not on argv).
- **AcpBackend**: `grok agent stdio` with live protocol handshake (CLI 0.2.x verified).
- **`auto`**: try ACP, fall back to Headless on failure.
- **SQLite WAL** under `~/.grok-proxy/gateway.db` for durable events and keys.

---

## Quick start

<p align="center">
  <img src="./assets/readme/section-quickstart.svg" width="100%" alt="Quick start section">
</p>

### Requirements

- Python **3.11+**
- [Grok Build CLI](https://x.ai) on `PATH` (or `GROK_BIN`), authenticated (`grok login` or `XAI_API_KEY`)

### Install & run

```bash
cd Grok-Build-Cli-Proxy
uv sync --all-extras

# API key is auto-generated on first start (~/.grok-proxy/)
uv run grok-proxy

# Optional: register WorkBuddy custom model
uv run grok-proxy --install-workbuddy
```

Startup prints **Base URL / API Key / Model ID** and writes:

| File | Purpose |
|------|---------|
| `~/.grok-proxy/api_key` | Bearer token |
| `~/.grok-proxy/client-config.json` | OpenAI-compatible client fields |
| `~/.grok-proxy/workbuddy-model.json` | WorkBuddy model entry |

### First request

```bash
export KEY="$(cat ~/.grok-proxy/api_key)"

curl -s http://127.0.0.1:8787/v1/responses \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Summarize this repository in 5 bullets",
    "x_grok": {"cwd": "'"$PWD"'", "workspace_mode": "read_only"}
  }' | jq .
```

Chat Completions (WorkBuddy / OpenAI SDK):

```bash
curl -s http://127.0.0.1:8787/v1/chat/completions \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-4.5",
    "messages": [{"role":"user","content":"List top-level files."}],
    "cwd": "'"$PWD"'",
    "stream": false
  }' | jq .
```

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

---

## Why not just `grok -p`?

| Need | Headless only | This gateway |
|------|---------------|--------------|
| OpenAI SDK / WorkBuddy | manual glue | ✅ |
| Long task: poll / cancel / SSE reconnect | ❌ | ✅ `/v1/responses` |
| Human approval without self-approve | hard | ✅ scoped keys + permission API |
| Workspace isolation (worktree) | ad-hoc | ✅ modes + locks |
| Other agents via MCP | ❌ | ✅ `--mcp-stdio` |
| Prompt not on process argv | often exposed | ✅ `--prompt-file` |

---

## API essentials

| Method | Path | Auth | Role |
|--------|------|------|------|
| GET | `/health` | no | Liveness |
| GET | `/ready` | no | DB + binary readiness |
| GET | `/metrics` | no | Prometheus text |
| GET | `/v1/models` | yes | Model list |
| GET | `/v1/connection` | yes (master key only) | Client config snapshot |
| POST | `/v1/chat/completions` | yes | Coding agent (compat) |
| POST | `/v1/responses` | yes | Create task |
| GET | `/v1/responses/{id}` | yes | Status / output |
| POST | `/v1/responses/{id}/cancel` | yes | Cancel |
| GET | `/v1/responses/{id}/events` | yes | SSE + `Last-Event-ID` |
| GET/POST | `/v1/permissions/{id}` | yes | Inspect / decide |
| GET/POST | `/v1/keys` | `admin:keys` | Scoped API keys |

### Background agent task

```json
{
  "input": "Fix failing tests",
  "background": true,
  "x_grok": {
    "cwd": "/path/to/repo",
    "workspace_mode": "worktree",
    "permission_policy": "ask"
  }
}
```

Then poll `GET /v1/responses/{id}` or stream `GET /v1/responses/{id}/events`.

### Scoped keys (no self-approve)

Master key (`GROK_PROXY_API_KEY`) has all scopes. Create a delegated agent key:

```bash
curl -s http://127.0.0.1:8787/v1/keys \
  -H "Authorization: Bearer $MASTER" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "codex-local",
    "workspace_allowlist": ["/Users/me/projects"],
    "max_concurrent": 1,
    "max_runtime_sec": 1800,
    "test": true
  }'
```

Default agent scopes **omit** `permission:approve` so tools cannot approve their own high-risk actions.

### Chat extensions

Top-level fields and nested `x_grok` are supported; **`x_grok` wins** on conflict.

| Field | Maps to |
|-------|---------|
| `cwd` / `working_directory` | workspace |
| `session_id` | Grok session resume |
| `max_turns` / `sandbox` / `worktree` | CLI flags |
| `always_approve` / `yolo` | auto-approve |
| `timeout_sec` | gateway kill timeout |
| `x_grok.workspace_mode` | `read_only` · `worktree` · `in_place` |

Response includes `grok.response_id` and `grok.session_id` for multi-turn resume.

### WorkBuddy

```bash
uv run grok-proxy --install-workbuddy
```

Or paste `~/.grok-proxy/workbuddy-model.json` into WorkBuddy models:

- **url** → Base URL  
- **apiKey** → API key  
- **id** → real model id from `grok models` (commonly `grok-4.5`, not the legacy alias `grok-build`)

### MCP

```bash
uv run grok-proxy --mcp-stdio
```

Tools: `grok_consult`, `grok_review`, `grok_delegate`, `grok_status`, `grok_cancel`, `grok_get_diff`, `grok_resume`.

### ACP backend

```bash
export GROK_PROXY_BACKEND=acp   # or: auto | headless
uv run grok-proxy

# handshake smoke (no long task)
uv run python scripts/probe_acp.py
```

See [docs/ACP.md](docs/ACP.md).

---

## Agent clients

Two integration modes — pick per client:

1. **OpenAI-compatible HTTP** — the client treats the gateway as a chat-completions model provider (`http://127.0.0.1:8787/v1`). Needs `uv run grok-proxy` running.
2. **MCP stdio** — the client spawns `grok-proxy --mcp-stdio` and calls tools (`grok_consult` / `grok_review` / `grok_delegate` …). No pre-started HTTP server needed; shares the same SQLite journal.

| Client | Mode | Config surface |
|--------|------|----------------|
| [WorkBuddy](#workbuddy-1) | HTTP model | `~/.workbuddy/models.json` (auto-install) |
| [Qoder](#qoder) | MCP stdio | Qoder Settings → MCP |
| [Codex](#codex) | MCP stdio **or** HTTP model | `~/.codex/config.toml` |
| [OpenCode](#opencode) | HTTP model | `opencode.json` |
| [Pi Agent](#pi-agent) | HTTP model | `~/.pi/agent/models.json` |
| [Trae CN](#trae-cn) | HTTP model (+ MCP) | 设置 → 模型 → 添加模型 |
| CodeBuddy | MCP stdio | same shape as Qoder |

Common setup (HTTP mode):

```bash
cd Grok-Build-Cli-Proxy
uv run grok-proxy                                   # gateway on 127.0.0.1:8787
export GROK_PROXY_API_KEY="$(cat ~/.grok-proxy/api_key)"
```

MCP command (both forms work; the absolute venv binary starts faster and avoids uv cache issues):

```text
/absolute/path/to/Grok-Build-Cli-Proxy/.venv/bin/grok-proxy --mcp-stdio
# or: uv run --directory /absolute/path/to/Grok-Build-Cli-Proxy grok-proxy --mcp-stdio
```

> **Important for HTTP-mode clients**: `/v1/chat/completions` runs a *coding agent*, and the working
> directory defaults to the proxy's `GROK_PROXY_DEFAULT_CWD` (or the directory the proxy was started
> from) when the client cannot send a `cwd` field. Generic clients (OpenCode / Pi / Trae) cannot —
> so either set `GROK_PROXY_DEFAULT_CWD=/path/to/project` before starting the proxy, or start the
> proxy from the project directory. Also raise the client's request timeout if configurable: agent
> runs take minutes, not seconds.

### WorkBuddy

```bash
uv run grok-proxy --install-workbuddy   # upserts ~/.workbuddy/models.json and starts the gateway
```

Or add a Custom model manually from `~/.grok-proxy/workbuddy-model.json`:
**url** = `http://127.0.0.1:8787/v1`, **apiKey** = contents of `~/.grok-proxy/api_key`,
**id** = `grok-4.5` (a real id from `grok models`, not the legacy alias `grok-build`).
Restart / refresh WorkBuddy models afterwards.

### Qoder

Settings → MCP → Add server (stdio):

```json
{
  "mcpServers": {
    "grok": {
      "command": "/absolute/path/to/Grok-Build-Cli-Proxy/.venv/bin/grok-proxy",
      "args": ["--mcp-stdio"]
    }
  }
}
```

Qoder then lists 7 tools. In chat, ask e.g. "use `grok_consult` to analyze this architecture" or
"delegate this refactor to `grok_delegate`, then poll `grok_status`". `grok_consult` / `grok_review`
are read-only; `grok_delegate` runs in an isolated git worktree with `permission_policy=ask` by default.

### Codex

**Option A — MCP server** (`~/.codex/config.toml`):

```toml
[mcp_servers.grok]
command = "/absolute/path/to/Grok-Build-Cli-Proxy/.venv/bin/grok-proxy"
args = ["--mcp-stdio"]
```

**Option B — use Grok as Codex's model** (OpenAI-compatible provider; gateway must be running):

```toml
# ~/.codex/config.toml
model = "grok-4.5"
model_provider = "grok-proxy"

[model_providers.grok-proxy]
name = "grok-proxy"
base_url = "http://127.0.0.1:8787/v1"
env_key = "GROK_PROXY_API_KEY"   # export it in the shell that launches codex
wire_api = "chat"
```

### OpenCode

Project `opencode.json` (or `~/.config/opencode/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "grok-proxy": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Grok Proxy (local)",
      "options": {
        "baseURL": "http://127.0.0.1:8787/v1",
        "apiKey": "{env:GROK_PROXY_API_KEY}"
      },
      "models": {
        "grok-4.5": { "name": "Grok 4.5 (Grok Build CLI)" }
      }
    }
  },
  "model": "grok-proxy/grok-4.5"
}
```

Alternatively run `opencode auth login` → *Other* → provider id `grok-proxy` to store the key instead
of the env placeholder. Since the gateway is itself a full agent, a lightweight OpenCode agent/mode
(few or no local tools) works best — let Grok do the editing.

### Pi Agent

`~/.pi/agent/models.json`:

```json
{
  "providers": {
    "grok-proxy": {
      "baseUrl": "http://127.0.0.1:8787/v1",
      "api": "openai-completions",
      "apiKey": "sk-gp-…",
      "compat": { "supportsDeveloperRole": false },
      "models": [
        { "id": "grok-4.5", "contextWindow": 131072, "maxTokens": 16384 }
      ]
    }
  }
}
```

Put the value of `~/.grok-proxy/api_key` into `apiKey` (or keep a placeholder and store the key via
`/login`). Then pick the model inside pi with `/model` → `grok-proxy/grok-4.5`.
`supportsDeveloperRole: false` makes pi send a plain `system` message, which the prompt builder maps cleanly.

### Trae CN

Trae 国内版支持自定义模型（OpenAI 兼容协议）：

1. 设置 → 模型 → **添加模型** → 选择 **自定义配置**
2. API 格式：**兼容 OpenAI**
3. 请求地址（Base URL）：`http://127.0.0.1:8787/v1`（Trae 会自行拼接 `/chat/completions`；若要求完整地址则填 `http://127.0.0.1:8787/v1/chat/completions`）
4. 模型 ID：`grok-4.5`，API Key：`~/.grok-proxy/api_key` 文件内容
5. 保存时 Trae 会发一次连通性测试请求 —— 网关和 grok CLI 登录态需可用（会消耗少量 token）

Trae 的 MCP 面板同样可以添加 stdio 服务器，命令与 [Qoder](#qoder) 一致。

### Security for third-party agents

Give each agent its own **scoped key** instead of the master key (no self-approval, workspace-limited):

```bash
curl -s http://127.0.0.1:8787/v1/keys \
  -H "Authorization: Bearer $(cat ~/.grok-proxy/api_key)" \
  -H "Content-Type: application/json" \
  -d '{"name": "opencode", "workspace_allowlist": ["'"$HOME"'/projects"], "max_concurrent": 1}'
```

Approve pending high-risk actions from `grok_delegate` / `permission_policy=ask` with the master key:

```bash
curl -s "http://127.0.0.1:8787/v1/permissions?status=pending" -H "Authorization: Bearer $MASTER"
curl -s -X POST "http://127.0.0.1:8787/v1/permissions/<id>/decision" \
  -H "Authorization: Bearer $MASTER" -H "Content-Type: application/json" \
  -d '{"decision": "allow_once"}'
```

---

## Security

Anyone with a Bearer token can run a **local coding agent** under allowed workspaces.

| Default | Value |
|---------|--------|
| Bind | `127.0.0.1` only |
| Auth | Bearer required |
| Workspace | prefer `read_only`; `in_place` off |
| Prompt | `--prompt-file` mode `0600` |
| Keys | hash-only storage for scoped keys |
| Agent scopes | no self-approve by default |

Do **not** expose this to the public internet without extra controls. Full notes: [docs/SECURITY.md](docs/SECURITY.md).

---

## Configuration

Common env vars (see [`.env.example`](.env.example) when present):

| Variable | Default | Meaning |
|----------|---------|---------|
| `GROK_PROXY_API_KEY` | auto | Master Bearer token |
| `GROK_PROXY_HOST` / `PORT` | `127.0.0.1` / `8787` | Bind |
| `GROK_BIN` | `grok` | CLI path |
| `GROK_PROXY_BACKEND` | `headless` | `headless` · `acp` · `auto` |
| `GROK_PROXY_DATABASE_PATH` | `~/.grok-proxy/gateway.db` | SQLite |
| `GROK_PROXY_CWD_ALLOWLIST` | empty | Allowed workspace prefixes |
| `GROK_PROXY_MAX_CONCURRENT` | `2` | Global parallel runs |
| `GROK_PROXY_DEFAULT_TIMEOUT_SEC` | `600` | Per-request timeout |
| `GROK_PROXY_DEFAULT_WORKSPACE_MODE` | `read_only` | Default workspace mode |
| `GROK_PROXY_ALLOW_IN_PLACE` | `false` | Allow source cwd mutation |
| `GROK_PROXY_PERMISSION_TIMEOUT_SEC` | `900` | Pending approval TTL |

---

## Development

```bash
uv sync --all-extras
uv run pytest -q -m "not grok_e2e"
# optional live ACP:
# RUN_GROK_E2E=1 uv run pytest -m grok_e2e -q
```

---

## Client integration & E2E

See the full per-client walkthroughs in [Agent clients](#agent-clients) above.

| Guide | Description |
|-------|-------------|
| [docs/clients/README.md](docs/clients/README.md) | Index + env setup |
| [docs/clients/curl.md](docs/clients/curl.md) | HTTP / curl |
| [docs/clients/openai-sdk.md](docs/clients/openai-sdk.md) | OpenAI Python SDK |
| [docs/clients/workbuddy.md](docs/clients/workbuddy.md) | WorkBuddy custom model |
| [docs/clients/codex-mcp.md](docs/clients/codex-mcp.md) | Codex / Qoder / CodeBuddy MCP |

```bash
./scripts/e2e_all.sh                 # MCP + ACP + unit tests (+ HTTP if proxy up)
./scripts/e2e_http.sh                # needs: uv run grok-proxy
E2E_LIVE_PROMPT=1 ./scripts/e2e_http.sh   # optional live Grok call
./scripts/e2e_mcp.sh
./scripts/e2e_acp.sh
```

## Docs

| Doc | Topic |
|-----|--------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module map |
| [docs/ADR-001-acp-runtime-responses-api.md](docs/ADR-001-acp-runtime-responses-api.md) | Why Scheme B |
| [docs/ACP.md](docs/ACP.md) | ACP protocol notes |
| [docs/API-CONTRACT-SNAPSHOT.md](docs/API-CONTRACT-SNAPSHOT.md) | API contract |
| [docs/UPGRADE-0.2.md](docs/UPGRADE-0.2.md) | v0.1 → v0.2 |
| [docs/RELEASE-NOTES-0.2.md](docs/RELEASE-NOTES-0.2.md) | Release notes |
| [docs/SECURITY.md](docs/SECURITY.md) | Security model |
| [docs/COMPAT-MATRIX.md](docs/COMPAT-MATRIX.md) | Compatibility |
| [CHANGELOG.md](CHANGELOG.md) | Changelog |

---

## Non-goals

- Multi-tenant public SaaS / billing  
- Full cloud container orchestration  
- Replacing every Grok internal event with OpenAI proprietary protocol  

---

## License

[MIT](LICENSE)
