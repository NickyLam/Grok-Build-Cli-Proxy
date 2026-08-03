# Release Notes — v0.2.0

**OpenGrokBuild** becomes a local **Agent Gateway**.

## Highlights

1. **OpenAI Responses API** — create, poll, cancel, SSE event replay  
2. **Orchestrator + backends** — Headless (`grok -p`), ACP skeleton (`grok agent stdio`), auto failover  
3. **Human-in-the-loop permissions** — policy engine + decision API  
4. **Scoped API keys** — hash-only storage; separate task vs approve scopes  
5. **Workspace safety** — allowlist, default read-only, optional worktree  
6. **MCP tools** — consult / review / delegate / status / cancel / diff  
7. **Observability** — `/metrics`, `/ready`, `X-Request-ID`, actor logs  

## Security notes

- Default bind remains **`127.0.0.1`** — do not expose without auth review  
- Prompts prefer **`--prompt-file`** with mode `0600` (not full text on argv)  
- API keys stored as **hashes** only  
- Agent keys **cannot self-approve** by default  
- `in_place` workspace mode **disabled by default**  
- Master key is full privilege — treat like root  

## Known limitations

- ACP protocol mapping is best-effort; validate against your Grok CLI version  
- Chat **stream** still uses runner SSE (not full orchestrator journal)  
- Real multi-client MCP Streamable HTTP is not the default transport  
- Grok E2E against live subscription is not gated in CI  

## Upgrade

See [UPGRADE-0.2.md](./UPGRADE-0.2.md).

## Install

```bash
uv sync --all-extras
uv run grok-proxy
```
