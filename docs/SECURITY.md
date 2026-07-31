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
| Always-approve | default **false**; Headless backend still forces approve (`grok -p`) |
| Public bind | rejected unless `GROK_PROXY_ALLOW_PUBLIC_BIND=1` |
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

## Key exposure surface

- The startup banner masks the API key by default; set `GROK_PROXY_BANNER_SHOW_KEY=1` to print it. The full key lives in `~/.grok-proxy/api_key` (0600).
- `GET /v1/connection` returns the plaintext master key and is therefore restricted to the master key itself (scoped keys get 403 `master_only`).
- Bootstrap exports `GROK_PROXY_API_KEY` into the process environment so uvicorn worker/reload child processes inherit it. Child processes spawned by the proxy can read it — do not run untrusted local processes under the same user.
- The scoped-key hash pepper is stored in the SQLite `meta` table, independent of the master key (legacy installs keep the old derived pepper so existing scoped keys stay valid).

## Audit

Permission decisions and key lifecycle write `audit_logs` rows in SQLite.
