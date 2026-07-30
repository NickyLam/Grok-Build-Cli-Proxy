from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from grok_proxy.grok_runner import map_usage


def new_completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


def sse_data(obj: dict[str, Any] | str) -> str:
    if isinstance(obj, str):
        return f"data: {obj}\n\n"
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def chunk_delta(
    *,
    completion_id: str,
    model: str,
    created: int,
    content: str | None = None,
    finish_reason: str | None = None,
    usage: dict[str, int] | None = None,
    grok: dict[str, Any] | None = None,
) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    choice: dict[str, Any] = {
        "index": 0,
        "delta": delta,
        "finish_reason": finish_reason,
    }
    body: dict[str, Any] = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [choice],
    }
    if usage is not None:
        body["usage"] = usage
    if grok is not None:
        body["grok"] = grok
    return body


async def stream_openai_sse(
    events: AsyncIterator[dict[str, Any]],
    *,
    model: str,
    include_thoughts: bool = False,
    include_usage: bool = False,
    on_session: Any | None = None,
) -> AsyncIterator[str]:
    """
    Convert Grok streaming-json events into OpenAI SSE lines.
    `on_session` optional callback(session_id: str | None).
    """
    completion_id = new_completion_id()
    created = int(time.time())
    saw_end = False
    session_id: str | None = None

    # role chunk first (OpenAI convention)
    yield sse_data(
        chunk_delta(
            completion_id=completion_id,
            model=model,
            created=created,
            content=None,
        )
        | {"choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
    )

    async for event in events:
        etype = event.get("type")
        if etype == "text":
            data = event.get("data") or ""
            if data:
                yield sse_data(
                    chunk_delta(
                        completion_id=completion_id,
                        model=model,
                        created=created,
                        content=str(data),
                    )
                )
        elif etype == "thought":
            if include_thoughts:
                data = event.get("data") or ""
                if data:
                    # Non-standard: prefix thoughts in content for simple clients
                    yield sse_data(
                        chunk_delta(
                            completion_id=completion_id,
                            model=model,
                            created=created,
                            content=f"\n[thinking] {data}",
                        )
                    )
        elif etype == "end":
            saw_end = True
            session_id = event.get("sessionId") or event.get("session_id")
            if on_session:
                on_session(session_id)
            usage_dict = None
            if include_usage or event.get("usage"):
                pt, ct, tt = map_usage(event.get("usage") if isinstance(event.get("usage"), dict) else None)
                usage_dict = {
                    "prompt_tokens": pt,
                    "completion_tokens": ct,
                    "total_tokens": tt,
                }
            grok_meta = {
                "session_id": session_id,
                "stop_reason": event.get("stopReason") or event.get("stop_reason"),
                "num_turns": event.get("num_turns") or event.get("numTurns"),
                "request_id": event.get("requestId") or event.get("request_id"),
                "raw_usage": event.get("usage"),
            }
            yield sse_data(
                chunk_delta(
                    completion_id=completion_id,
                    model=model,
                    created=created,
                    finish_reason="stop",
                    usage=usage_dict if include_usage else None,
                    grok=grok_meta,
                )
            )
        elif etype == "error":
            msg = event.get("message") or "Grok stream error"
            # Emit a final error-ish chunk then DONE
            yield sse_data(
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": f"\n[error] {msg}"},
                            "finish_reason": "stop",
                        }
                    ],
                    "grok": {
                        "session_id": session_id,
                        "error": msg,
                        "code": event.get("code"),
                    },
                }
            )
            yield sse_data("[DONE]")
            return

    if not saw_end:
        yield sse_data(
            chunk_delta(
                completion_id=completion_id,
                model=model,
                created=created,
                finish_reason="stop",
                grok={"session_id": session_id},
            )
        )
    yield sse_data("[DONE]")
