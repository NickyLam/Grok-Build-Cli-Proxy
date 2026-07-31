"""Grok execution backends (headless CLI, ACP, fakes)."""

from grok_proxy.backends.base import (
    BackendCapabilities,
    BackendError,
    BackendEvent,
    BackendSession,
    BackendSessionRequest,
    GrokBackend,
    PermissionDecisionPayload,
    PromptInput,
)
from grok_proxy.backends.fake import FakeBackend
from grok_proxy.backends.headless import HeadlessBackend

__all__ = [
    "BackendCapabilities",
    "BackendError",
    "BackendEvent",
    "BackendSession",
    "BackendSessionRequest",
    "FakeBackend",
    "GrokBackend",
    "HeadlessBackend",
    "PermissionDecisionPayload",
    "PromptInput",
]
