# Risk Register (Scheme B)

| ID | Risk | Impact | Mitigation |
|----|------|--------|------------|
| R1 | ACP protocol drift across Grok CLI versions | High | Pin CLI docs; feature-detect; HeadlessBackend fallback |
| R2 | Residual child processes after cancel/timeout | High | Process groups, graceful+force kill, shutdown cleanup |
| R3 | Prompt leakage via `ps` / process args | High | Always use `--prompt-file` with mode `0600` |
| R4 | Permission bypass by untrusted callers | Critical | Server hard limits ∩ key scopes ∩ policy; no client-only approve |
| R5 | Two writers mutate same source workspace | High | Default worktree; exclusive workspace locks |
| R6 | SSE reconnect drops events | High | Durable event journal + sequence numbers + Last-Event-ID |
| R7 | SQLite corruption under concurrent writers | Medium | WAL mode, short transactions, single-writer discipline |
| R8 | Raw model thoughts leak on public API | Medium | Default redact; debug flag local-only |
| R9 | API key stored in plaintext | High | Hash-only storage for scoped keys; file mode 0600 for bootstrap key |
| R10 | Default bind / always-approve unsafe for remote | Critical | Default `127.0.0.1`; document `always_approve` risks |
