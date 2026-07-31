from __future__ import annotations

import pytest

from grok_proxy.errors import ProxyError
from grok_proxy.runtime.state_machine import ResponseStateMachine, ResponseStatus


def test_happy_path():
    sm = ResponseStateMachine()
    assert sm.status == ResponseStatus.QUEUED
    sm.transition(ResponseStatus.IN_PROGRESS)
    sm.transition(ResponseStatus.COMPLETED)
    assert sm.is_terminal


def test_illegal_transition():
    sm = ResponseStateMachine(ResponseStatus.COMPLETED)
    with pytest.raises(ProxyError) as ei:
        sm.transition(ResponseStatus.IN_PROGRESS)
    assert ei.value.code == "illegal_status_transition"


def test_cancel_idempotent():
    sm = ResponseStateMachine(ResponseStatus.IN_PROGRESS)
    sm.transition(ResponseStatus.CANCELLED)
    sm.transition(ResponseStatus.CANCELLED)
    assert sm.status == ResponseStatus.CANCELLED


def test_waiting_for_approval_cycle():
    sm = ResponseStateMachine(ResponseStatus.IN_PROGRESS)
    sm.transition(ResponseStatus.WAITING_FOR_APPROVAL)
    sm.transition(ResponseStatus.IN_PROGRESS)
    sm.transition(ResponseStatus.COMPLETED)
