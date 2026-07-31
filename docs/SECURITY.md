# Security

## Threat model (local agent gateway)

Assume:

- Callers may be less trusted agents (Codex, automation)
- Grok can run tools that modify files and execute shell
- Network exposure multiplies risk

## Defaults

| Control | Default |
|---------|---------|
| Bind address | `127.0.0.1` |
| Auth | Bearer required |
| Workspace | `read_only` preferred |
| `in_place` | disabled |
| Always-approve | server default (often true for headless CI) |
| Key storage | SHA-256 hash + pepper |
| Prompt argv | use `--prompt-file` |

## Hard rules

1. **Never** ship with open bind (`0.0.0.0`) + weak/no auth  
2. **Never** give untrusted agents `permission:approve`  
3. Prefer **worktree** for write tasks  
4. Keep `GROK_PROXY_CWD_ALLOWLIST` tight  
5. Rotate master key if leaked; revoke scoped keys via API  

## Scope separation

| Role | Suggested scopes |
|------|------------------|
| Coding agent | `response:create/read/cancel`, `event:read`, `workspace:read`, `tool:execute` |
| Human approver | `permission:read/approve`, `response:read`, `event:read` |
| Admin | `admin:keys` + master key offline |

## Secrets redaction

Headless backend redacts common token patterns from error surfaces. Do not log raw Authorization headers.

## Audit

Permission decisions and key lifecycle write `audit_logs` rows in SQLite.
