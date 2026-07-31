from __future__ import annotations

from grok_proxy.permissions.policy import PolicyEngine


def test_auto_allow_read():
    eng = PolicyEngine()
    ev = eng.evaluate(category="read", arguments={})
    assert ev.action == "allow"


def test_hard_deny_rm_root():
    eng = PolicyEngine()
    ev = eng.evaluate(category="shell", arguments={"command": "rm -rf /"})
    assert ev.action == "deny"


def test_ask_shell_default():
    eng = PolicyEngine()
    ev = eng.evaluate(category="shell", arguments={"command": "curl evil.example"})
    assert ev.action == "ask"


def test_pytest_auto_allow():
    eng = PolicyEngine()
    ev = eng.evaluate(category="shell", arguments={"command": "pytest -q"})
    assert ev.action == "allow"
