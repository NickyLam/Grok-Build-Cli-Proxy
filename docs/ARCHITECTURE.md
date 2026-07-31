# Architecture (v0.2 Scheme B)

```text
┌────────────────────────────────────────────────────────┐
│                      API Gateway                       │
│  /v1/chat/completions  /v1/responses  /v1/permissions  │
│  /v1/models  /health  MCP stdio                        │
└─────────────────────────┬──────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────┐
│                 Response Orchestrator                  │
│  state machine · event journal · cancel · timeout      │
│  permission wait · workspace bind                      │
└──────────────┬──────────────────┬──────────────────────┘
               │                  │
      ┌────────▼────────┐ ┌───────▼────────┐
      │   AcpBackend    │ │ HeadlessBackend│
      │  grok agent     │ │  grok -p file  │
      └────────┬────────┘ └───────┬────────┘
               │                  │
               └────────┬─────────┘
                        ▼
                 Grok Build CLI
```

## Modules

| Package | Role |
|---------|------|
| `api/` | FastAPI routers |
| `backends/` | GrokBackend protocol, Headless, ACP, Fake |
| `runtime/` | Orchestrator, state machine, process manager, commands |
| `storage/` | SQLite WAL, migrations, repositories |
| `permissions/` | Policy + broker |
| `workspace/` | Allowlist, worktree, locks, diff |
| `protocol/` | Response / event / extension models |
| `mcp/` | MCP tool surface over orchestrator |

## Data plane

- **Response** — unit of work (queued → … → terminal)
- **Event** — ordered journal per response (`sequence_number`)
- **Session** — backend session identity + cwd binding
- **Permission** — pending/decided human-in-the-loop record
