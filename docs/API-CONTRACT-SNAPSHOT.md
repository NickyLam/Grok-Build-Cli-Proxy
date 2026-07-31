# API Contract Snapshot (v0.2)

## Auth

- Header: `Authorization: Bearer <key>` (also `x-api-key`)
- **Master key** (`GROK_PROXY_API_KEY`): all scopes
- **Scoped keys** (`gp_live_*` / `gp_test_*`): hash-only in SQLite; scopes + workspace allowlist
- Unauthenticated: `401`
- Missing scope: `403` `insufficient_scope`
- Key cwd outside allowlist: `403` `key_cwd_forbidden`

### Scopes

| Scope | Capability |
|-------|------------|
| `response:create` | Create responses / chat |
| `response:read` | Get response |
| `response:cancel` | Cancel |
| `event:read` | SSE events |
| `permission:read` | View permission |
| `permission:approve` | Decide permission |
| `workspace:read` / `workspace:write` | Workspace modes |
| `tool:execute` | Tool execution path |
| `admin:keys` | Manage API keys |

## Endpoints

### Health

- `GET /health` → `{ status, version, in_flight, max_concurrent, default_model, backend, ... }`
- `GET /ready` → `{ status: ready|not_ready, checks: { database, grok_bin } }`

### Chat Completions (compat)

`POST /v1/chat/completions`

- Body: OpenAI chat body + extensions (`cwd`, `session_id`, `max_turns`, …) or `x_grok`
- Non-stream: routes through Response Orchestrator; response includes `grok.response_id`
- Stream: OpenAI SSE via headless runner (v0.1 compatible)

### Responses

`POST /v1/responses`

```json
{
  "model": "grok-4.5",
  "input": "string | array",
  "stream": false,
  "background": false,
  "previous_response_id": null,
  "metadata": {},
  "x_grok": {
    "cwd": "/repo",
    "workspace_mode": "read_only",
    "permission_policy": "always_approve",
    "session_id": null
  }
}
```

`GET /v1/responses/{id}` → `ResponseObject`

`POST /v1/responses/{id}/cancel` → cancelled (idempotent when already terminal)

`GET /v1/responses/{id}/events?after=N`  
Headers: `Last-Event-ID: N`  
SSE: `id`, `event`, `data` per journal event

### Permissions

`GET /v1/permissions/{id}`

`POST /v1/permissions/{id}/decision`

```json
{ "decision": "allow_once|allow_for_session|deny_once|deny_with_feedback|cancel_run", "feedback": null, "scope": null }
```

## Response statuses

`queued` → `in_progress` ⇄ `waiting_for_approval` → `completed` | `failed` | `cancelled` | `incomplete`

## Event types (journal)

Standard: `response.created`, `response.queued`, `response.in_progress`, `response.output_text.delta`, `response.output_text.done`, `response.completed`, `response.failed`, `response.cancelled`, `response.incomplete`

Grok: `response.tool_call.*`, `response.plan.updated`, `response.permission.*`, `response.usage.updated`, `response.workspace.created`
