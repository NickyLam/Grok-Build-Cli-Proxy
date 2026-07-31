"""Pure helpers for mapping ACP session/update payloads (unit-testable)."""

from __future__ import annotations

from typing import Any

from grok_proxy.backends.base import BackendEvent


def map_session_update(
    params: dict[str, Any],
    *,
    include_thoughts: bool = False,
) -> BackendEvent | None:
    update = params.get("update") if isinstance(params.get("update"), dict) else params
    if not isinstance(update, dict):
        return None
    kind = str(
        update.get("sessionUpdate") or update.get("type") or update.get("updateType") or ""
    ).lower()
    content = update.get("content") if isinstance(update.get("content"), dict) else {}
    text = ""
    if isinstance(content, dict):
        text = str(content.get("text") or "")
    elif isinstance(update.get("text"), str):
        text = update["text"]

    if kind in ("agent_message_chunk", "agentmessagechunk", "message_chunk", "message"):
        return BackendEvent(type="text", data={"text": text}, raw=params)
    if kind in ("agent_thought_chunk", "agentthoughtchunk", "thought_chunk", "thought"):
        if include_thoughts and text:
            return BackendEvent(type="text", data={"text": text, "thought": True}, raw=params)
        return None
    if "tool" in kind and (
        "start" in kind or kind in ("tool_call", "toolcall") or kind.endswith("tool_call")
    ):
        return BackendEvent(
            type="tool_call",
            data={
                "id": update.get("toolCallId") or update.get("id"),
                "name": update.get("title") or update.get("name") or update.get("toolName"),
                "arguments": update.get("rawInput")
                or update.get("arguments")
                or update.get("input")
                or {},
                "title": update.get("title"),
            },
            raw=params,
        )
    if "tool" in kind and ("update" in kind or "progress" in kind):
        return BackendEvent(
            type="tool_update",
            data={
                "id": update.get("toolCallId") or update.get("id"),
                "status": update.get("status"),
                "partial": update.get("content") or update.get("rawOutput"),
            },
            raw=params,
        )
    if "tool" in kind and ("end" in kind or "complete" in kind or "result" in kind):
        return BackendEvent(
            type="tool_result",
            data={
                "id": update.get("toolCallId") or update.get("id"),
                "result": update.get("rawOutput") or update.get("content") or update.get("result"),
                "status": update.get("status") or "completed",
            },
            raw=params,
        )
    if "plan" in kind or "todo" in kind:
        return BackendEvent(type="plan", data={"plan": update}, raw=params)
    if "permission" in kind:
        return BackendEvent(
            type="permission_request",
            data={
                "id": update.get("requestId") or update.get("permissionId") or update.get("id"),
                "category": update.get("category") or update.get("kind") or "unknown",
                "title": update.get("title") or update.get("message") or "Permission required",
                "arguments": update.get("arguments") or update.get("input") or {},
                "risk": update.get("risk") or "medium",
                "options": update.get("options") or [],
            },
            raw=params,
        )
    return None


def normalize_usage(usage: dict[str, Any]) -> dict[str, Any]:
    out = dict(usage)
    mapping = {
        "inputTokens": "input_tokens",
        "outputTokens": "output_tokens",
        "totalTokens": "total_tokens",
        "cachedReadTokens": "cached_tokens",
        "reasoningTokens": "reasoning_tokens",
        "numTurns": "num_turns",
    }
    for src, dst in mapping.items():
        if src in usage and dst not in usage:
            out[dst] = usage[src]
    return out
