from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: str | list[Any] | None = None
    name: str | None = None

    def text_content(self) -> str:
        if self.content is None:
            return ""
        if isinstance(self.content, str):
            return self.content
        # OpenAI multimodal content blocks
        parts: list[str] = []
        for block in self.content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and "text" in block:
                    parts.append(str(block["text"]))
                elif "text" in block:
                    parts.append(str(block["text"]))
            else:
                text = getattr(block, "text", None)
                if text is not None:
                    parts.append(str(text))
        return "\n".join(parts)


class StreamOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    include_usage: bool | None = None


class ChatCompletionRequest(BaseModel):
    """OpenAI chat.completions request + Grok proxy extensions."""

    model_config = ConfigDict(extra="allow")

    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False
    stream_options: StreamOptions | None = None

    # Grok proxy extensions (also accepted via extra_body)
    cwd: str | None = None
    working_directory: str | None = None
    session_id: str | None = None
    max_turns: int | None = None
    sandbox: str | None = None
    rules: str | None = None
    yolo: bool | None = None
    always_approve: bool | None = None
    tools_allow: list[str] | None = None
    tools_deny: list[str] | None = None
    permission_mode: str | None = None
    allow: list[str] | None = None
    deny: list[str] | None = None
    reasoning_effort: str | None = None
    worktree: str | bool | None = None
    timeout_sec: int | None = None
    include_thoughts: bool = False

    @field_validator("messages")
    @classmethod
    def non_empty_messages(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if not v:
            raise ValueError("messages must be a non-empty array")
        return v

    @model_validator(mode="after")
    def normalize_cwd(self) -> ChatCompletionRequest:
        if self.cwd is None and self.working_directory is not None:
            self.cwd = self.working_directory
        return self

    def resolved_always_approve(self, default: bool) -> bool:
        if self.always_approve is not None:
            return self.always_approve
        if self.yolo is not None:
            return self.yolo
        return default


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatMessageOut(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class Choice(BaseModel):
    index: int = 0
    message: ChatMessageOut
    finish_reason: str | None = "stop"


class GrokMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str | None = None
    stop_reason: str | None = None
    num_turns: int | None = None
    request_id: str | None = None
    raw_usage: dict[str, Any] | None = None
    exit_code: int | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)
    grok: GrokMeta | None = None


class ModelCard(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str = "xai"


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelCard]
