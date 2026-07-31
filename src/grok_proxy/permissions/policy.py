from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

# NOTE: this engine is a best-effort guardrail against obviously destructive
# actions. Pattern matching cannot catch indirection (variables, base64,
# nested shells) — it must never replace human approval for untrusted input.

DecisionAction = Literal["allow", "deny", "ask"]


@dataclass
class PolicyRule:
    action: DecisionAction
    category: str | None = None  # shell, file_write, network, mcp, read
    path_glob: str | None = None
    command_glob: str | None = None
    command_regex: str | None = None
    domain_glob: str | None = None
    mcp_tool_glob: str | None = None
    risk: str | None = None


@dataclass
class PolicyConfig:
    """Deny-first policy. Client may only tighten, never expand."""

    hard_deny: list[PolicyRule] = field(default_factory=list)
    auto_allow: list[PolicyRule] = field(default_factory=list)
    ask: list[PolicyRule] = field(default_factory=list)
    default_action: DecisionAction = "ask"


@dataclass
class PolicyEvaluation:
    action: DecisionAction
    matched_rule: str
    risk: str
    category: str


DEFAULT_POLICY = PolicyConfig(
    hard_deny=[
        # Recursive/any rm of root or home (covers -rf/-fr/-r -f, ~, $HOME, trailing flags)
        PolicyRule(
            action="deny",
            command_regex=(
                r"^(?:sudo\s+)?rm\s+(?:-{1,2}[\w-]+\s+)*"
                r"(?:/|/\*|~|~/|\$HOME/?)(?:\s+-{1,2}[\w-]+)*\s*$"
            ),
        ),
        PolicyRule(action="deny", command_regex=r"^(?:sudo\s+)?mkfs"),
        PolicyRule(action="deny", command_glob="dd if=*"),
        PolicyRule(action="deny", command_regex=r"^(?:sudo\s+)?dd\s+.*\bof=/dev/"),
        # Fork bomb
        PolicyRule(action="deny", command_regex=r":\(\)\s*\{"),
        # Pipe remote script straight into a shell
        PolicyRule(
            action="deny",
            command_regex=r"\b(?:curl|wget)\s+[^|;&]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b",
        ),
        PolicyRule(action="deny", command_regex=r"^(?:sudo\s+)?chmod\s+(?:-[\w]+\s+)*777\s+/\s*$"),
        PolicyRule(action="deny", path_glob="~/.ssh/*"),
        PolicyRule(action="deny", path_glob="**/id_rsa*"),
        PolicyRule(action="deny", path_glob="**/.env"),
        PolicyRule(action="deny", path_glob="**/credentials*"),
    ],
    auto_allow=[
        PolicyRule(action="allow", category="read"),
        PolicyRule(action="allow", category="grep"),
        PolicyRule(action="allow", category="list"),
        PolicyRule(action="allow", command_glob="pytest*"),
        PolicyRule(action="allow", command_glob="python -m pytest*"),
        PolicyRule(action="allow", command_glob="uv run pytest*"),
        PolicyRule(action="allow", command_glob="git status*"),
        PolicyRule(action="allow", command_glob="git diff*"),
        PolicyRule(action="allow", command_glob="git log*"),
    ],
    ask=[
        PolicyRule(action="ask", category="shell"),
        PolicyRule(action="ask", category="file_write"),
        PolicyRule(action="ask", category="network"),
        PolicyRule(action="ask", category="mcp"),
    ],
    default_action="ask",
)


class PolicyEngine:
    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.config = config or DEFAULT_POLICY

    def evaluate(
        self,
        *,
        category: str,
        risk: str = "medium",
        arguments: dict[str, Any] | None = None,
        force_ask: bool = False,
    ) -> PolicyEvaluation:
        arguments = arguments or {}
        command = str(arguments.get("command") or arguments.get("cmd") or "")
        # Normalize whitespace so "rm  -rf   /" cannot dodge patterns
        command = " ".join(command.split())
        path = str(arguments.get("path") or arguments.get("file") or "")
        domain = str(arguments.get("domain") or arguments.get("url") or "")
        mcp_tool = str(arguments.get("tool") or arguments.get("mcp_tool") or "")

        if force_ask:
            return PolicyEvaluation(action="ask", matched_rule="force_ask", risk=risk, category=category)

        for rule in self.config.hard_deny:
            if self._match(rule, category, command, path, domain, mcp_tool, risk):
                return PolicyEvaluation(
                    action="deny",
                    matched_rule="hard_deny",
                    risk=risk,
                    category=category,
                )

        for rule in self.config.auto_allow:
            if self._match(rule, category, command, path, domain, mcp_tool, risk):
                return PolicyEvaluation(
                    action="allow",
                    matched_rule="auto_allow",
                    risk=risk,
                    category=category,
                )

        for rule in self.config.ask:
            if self._match(rule, category, command, path, domain, mcp_tool, risk):
                return PolicyEvaluation(
                    action="ask",
                    matched_rule="ask",
                    risk=risk,
                    category=category,
                )

        return PolicyEvaluation(
            action=self.config.default_action,
            matched_rule="default",
            risk=risk,
            category=category,
        )

    @staticmethod
    def _match(
        rule: PolicyRule,
        category: str,
        command: str,
        path: str,
        domain: str,
        mcp_tool: str,
        risk: str,
    ) -> bool:
        if rule.category and rule.category != category:
            return False
        if rule.risk and rule.risk != risk:
            return False
        if rule.command_regex and not re.search(rule.command_regex, command):
            return False
        if rule.command_glob and not fnmatch.fnmatch(command, rule.command_glob):
            # also try regex-ish prefix for shell
            if not re.match(fnmatch.translate(rule.command_glob), command):
                return False
        if rule.path_glob and not PolicyEngine._path_matches(path, rule.path_glob):
            return False
        if rule.domain_glob and not fnmatch.fnmatch(domain, rule.domain_glob):
            return False
        if rule.mcp_tool_glob and not fnmatch.fnmatch(mcp_tool, rule.mcp_tool_glob):
            return False
        # category-only rule
        if not any(
            [
                rule.command_glob,
                rule.command_regex,
                rule.path_glob,
                rule.domain_glob,
                rule.mcp_tool_glob,
                rule.risk,
            ]
        ) and rule.category:
            return rule.category == category
        if (
            rule.command_glob
            or rule.command_regex
            or rule.path_glob
            or rule.domain_glob
            or rule.mcp_tool_glob
        ):
            return True
        return bool(rule.category)

    @staticmethod
    def _path_matches(path: str, glob: str) -> bool:
        """Glob match with ~ expansion on both sides."""
        if not path:
            return False
        candidates = {path, os.path.expanduser(path)}
        globs = {glob, os.path.expanduser(glob), glob.replace("**/", "")}
        return any(fnmatch.fnmatch(p, g) for p in candidates for g in globs)
