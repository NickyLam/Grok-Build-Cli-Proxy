# ADR-001: ACP Runtime + OpenAI Responses API

## Status

Accepted (v0.2)

## Context

v0.1 exposes Grok Build only through `grok -p` (headless one-shot) behind
OpenAI Chat Completions. That path cannot:

- surface tool / plan / permission events to callers;
- pause for human approval and resume the same session;
- run long background tasks with cancel, reconnect, and status query;
- separate task-initiator authority from approval authority.

## Decision

Adopt **Scheme B**:

1. **Response Orchestrator** as the single execution core for HTTP and MCP.
2. **`/v1/responses`** as the primary task API (status, cancel, event replay).
3. **Backend Protocol** with:
   - **AcpBackend** — primary runtime via `grok agent` (stdio first);
   - **HeadlessBackend** — compatibility / fallback via `grok -p` + prompt file.
4. Keep **`/v1/chat/completions`** as a thin compatibility layer over the same
   orchestrator (`CreateResponseCommand`).

## Consequences

- Requires SQLite-backed response/event journal and a strict response state machine.
- Chat Completions remains supported for WorkBuddy / OpenAI SDK clients.
- Permission broker and workspace isolation become first-class gateway concerns.
- Prompt text must not appear in process argument lists (use `--prompt-file`).

## Alternatives considered

| Option | Why not |
|--------|---------|
| A: Only enhance `grok -p` | No real interactive approval / long session |
| C: ACP-only gateway | Breaks WorkBuddy and OpenAI SDK users |
