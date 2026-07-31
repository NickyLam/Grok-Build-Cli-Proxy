from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from grok_proxy.storage.models import ResponseRecord


class GrokExtensionsModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    cwd: str | None = None
    session_id: str | None = None
    max_turns: int | None = None
    sandbox: str | None = None
    rules: str | None = None
    always_approve: bool | None = None
    tools_allow: list[str] | None = None
    tools_deny: list[str] | None = None
    permission_mode: str | None = None
    allow: list[str] | None = None
    deny: list[str] | None = None
    reasoning_effort: str | None = None
    worktree: str | bool | None = None
    timeout_sec: int | None = None
    workspace_mode: Literal["read_only", "in_place", "worktree", "temporary_copy"] | None = None
    permission_policy: Literal["always_approve", "ask", "server"] | None = None
    backend: Literal["auto", "acp", "headless"] | None = None
    include_thoughts: bool = False


class CreateResponseRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str | None = None
    input: str | list[Any]
    stream: bool = False
    background: bool = False
    previous_response_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    x_grok: GrokExtensionsModel | None = None
    # top-level aliases for convenience
    cwd: str | None = None
    session_id: str | None = None

    def input_text(self) -> str:
        if isinstance(self.input, str):
            return self.input
        parts: list[str] = []
        for item in self.input:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "input_text" and "text" in item:
                    parts.append(str(item["text"]))
                elif "content" in item:
                    parts.append(str(item["content"]))
                elif "text" in item:
                    parts.append(str(item["text"]))
        return "\n".join(parts)


class ResponseUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    extra: dict[str, Any] | None = None


class ResponseError(BaseModel):
    code: str | None = None
    message: str | None = None


class ResponseObject(BaseModel):
    id: str
    object: Literal["response"] = "response"
    status: str
    model: str
    created_at: int
    output: list[dict[str, Any]] = Field(default_factory=list)
    usage: ResponseUsage | None = None
    error: ResponseError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    x_grok: dict[str, Any] = Field(default_factory=dict)


def response_record_to_object(rec: ResponseRecord) -> ResponseObject:
    usage = None
    if rec.usage_json:
        usage = ResponseUsage(
            input_tokens=int(
                rec.usage_json.get("input_tokens")
                or rec.usage_json.get("prompt_tokens")
                or 0
            ),
            output_tokens=int(
                rec.usage_json.get("output_tokens")
                or rec.usage_json.get("completion_tokens")
                or 0
            ),
            total_tokens=int(rec.usage_json.get("total_tokens") or 0),
            extra=rec.usage_json,
        )
    err = None
    if rec.error_code or rec.error_message:
        err = ResponseError(code=rec.error_code, message=rec.error_message)
    xg = dict(rec.x_grok_json or {})
    xg.update(
        {
            "backend": rec.backend,
            "session_id": rec.session_id,
            "source_cwd": rec.source_cwd,
            "run_cwd": rec.run_cwd,
            "workspace_mode": rec.workspace_mode,
            "text": rec.text,
        }
    )
    output = rec.output_json or []
    if not output and rec.text:
        output = [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": rec.text}],
            }
        ]
    return ResponseObject(
        id=rec.id,
        status=rec.status,
        model=rec.model,
        created_at=int(rec.created_at),
        output=output,
        usage=usage,
        error=err,
        metadata=rec.metadata_json or {},
        x_grok=xg,
    )
