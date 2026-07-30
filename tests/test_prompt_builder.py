from __future__ import annotations

import pytest

from grok_proxy.errors import ProxyError
from grok_proxy.models import ChatMessage
from grok_proxy.prompt_builder import build_prompt


def test_single_user_raw():
    prompt, rules = build_prompt(
        [ChatMessage(role="user", content="hello")],
        session_id=None,
    )
    assert prompt == "hello"
    assert rules is None


def test_system_becomes_rules():
    prompt, rules = build_prompt(
        [
            ChatMessage(role="system", content="Be concise."),
            ChatMessage(role="user", content="Hi"),
        ],
        session_id=None,
    )
    assert prompt == "Hi"
    assert rules == "Be concise."


def test_multi_turn_linearized():
    prompt, _ = build_prompt(
        [
            ChatMessage(role="user", content="a"),
            ChatMessage(role="assistant", content="b"),
            ChatMessage(role="user", content="c"),
        ],
        session_id=None,
    )
    assert "User: a" in prompt
    assert "Assistant: b" in prompt
    assert "User: c" in prompt


def test_resume_uses_last_user_only():
    prompt, rules = build_prompt(
        [
            ChatMessage(role="user", content="old"),
            ChatMessage(role="assistant", content="reply"),
            ChatMessage(role="user", content="continue"),
        ],
        session_id="abc",
    )
    assert prompt == "continue"
    assert rules is None


def test_resume_rejects_non_user_last():
    with pytest.raises(ProxyError) as ei:
        build_prompt(
            [ChatMessage(role="assistant", content="x")],
            session_id="abc",
        )
    assert ei.value.status_code == 400
