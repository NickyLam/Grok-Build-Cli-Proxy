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
  <a href="#security">Security</a> ·
  <a href="docs/UPGRADE-0.2.md">Upgrade</a> ·
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
| GET | `/v1/connection` | yes | Client config snapshot |
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
