# Upgrade Guide: v0.1 → v0.2

## Summary

v0.2 turns the Chat Completions CLI proxy into an **Agent Gateway**:

- Shared **Response Orchestrator**
- New **`/v1/responses`** lifecycle API
- SQLite event journal under `~/.grok-proxy/gateway.db`
- Scoped API keys, permissions, workspace modes, MCP tools

**Chat Completions remains compatible** for WorkBuddy / OpenAI SDK clients using the master key.

## Breaking / behavior changes

| Area | v0.1 | v0.2 |
|------|------|------|
| Non-stream chat | Direct `GrokRunner.run` | Orchestrator + HeadlessBackend (stream-json) |
| Prompt on argv | `-p <full prompt>` | Prefer `--prompt-file` (0600 temp file) |
| Response metadata | `grok.session_id` only | Also `grok.response_id` |
| Persistence | Memory only | SQLite WAL journal |
| Default workspace | implicit cwd | Prefer `read_only`; `in_place` off by default |

Stream chat (`stream: true`) still uses the OpenAI SSE path via `GrokRunner.stream` for WorkBuddy compatibility.

## Config migration

Existing env vars still work. New optional vars:

```bash
export GROK_PROXY_BACKEND=headless   # or acp | auto
export GROK_PROXY_DATABASE_PATH=~/.grok-proxy/gateway.db
export GROK_PROXY_DEFAULT_WORKSPACE_MODE=read_only
export GROK_PROXY_ALLOW_IN_PLACE=0
export GROK_PROXY_PERMISSION_TIMEOUT_SEC=900
```

No mandatory config change for v0.1 clients.

## API migration

### Stay on Chat Completions

```http
POST /v1/chat/completions
Authorization: Bearer <master-or-scoped-key>
```

Optional nested extensions:

```json
{
  "messages": [{"role": "user", "content": "…"}],
  "x_grok": {
    "cwd": "/repo",
    "workspace_mode": "read_only",
    "session_id": null
  }
}
```

`x_grok` wins over top-level `cwd` / `session_id` when both are set.

### Prefer Responses API (long tasks)

```http
POST /v1/responses
```

```json
{
  "input": "Fix failing tests",
  "background": true,
  "x_grok": {
    "cwd": "/repo",
    "workspace_mode": "worktree",
    "permission_policy": "ask"
  }
}
```

Then:

- `GET /v1/responses/{id}`
- `GET /v1/responses/{id}/events` (SSE, `Last-Event-ID`)
- `POST /v1/responses/{id}/cancel`
- `POST /v1/permissions/{id}/decision` when `waiting_for_approval`

## Database

First start creates SQLite schema via migrations (v1 tables + v2 key columns).

Backup:

```bash
cp ~/.grok-proxy/gateway.db ~/.grok-proxy/gateway.db.bak
```

## Scoped keys

Master key retains full power. Create agent keys without approval scope:

```bash
curl -s localhost:8787/v1/keys \
  -H "Authorization: Bearer $MASTER" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "codex",
    "workspace_allowlist": ["/Users/me/projects"],
    "max_concurrent": 1,
    "max_runtime_sec": 1800,
    "test": true
  }'
```

Store the returned `api_key` immediately; it is not shown again.

## Backend selection

| Value | Behavior |
|-------|----------|
| `headless` (default) | `grok -p --prompt-file` |
| `acp` | `grok agent stdio` |
| `auto` | ACP with Headless failover if handshake fails |

## Rollback

1. Pin package to `0.1.x`
2. Remove reliance on `/v1/responses` and scoped keys
3. SQLite file can remain unused

## Checklist after upgrade

- [ ] `GET /health` and `GET /ready` OK
- [ ] Chat non-stream with master key
- [ ] Chat stream (WorkBuddy)
- [ ] `POST /v1/responses` smoke
- [ ] Optional: create scoped key and verify 403 without `permission:approve`
