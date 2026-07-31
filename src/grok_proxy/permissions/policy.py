from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any, Literal

DecisionAction = Literal["allow", "deny", "ask"]


@dataclass
class PolicyRule:
    action: DecisionAction
    category: str | None = None  # shell, file_write, network, mcp, read
    path_glob: str | None = None
    command_glob: str | None = None
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
        PolicyRule(action="deny", command_glob="rm -rf /*"),
        PolicyRule(action="deny", command_glob="rm -rf /"),
        PolicyRule(action="deny", command_glob="mkfs*"),
        PolicyRule(action="deny", command_glob="dd if=*"),
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
        if rule.command_glob and not fnmatch.fnmatch(command, rule.command_glob):
            # also try regex-ish prefix for shell
            if not re.match(fnmatch.translate(rule.command_glob), command):
                return False
        if rule.path_glob and not (
            fnmatch.fnmatch(path, rule.path_glob) or fnmatch.fnmatch(path, rule.path_glob.replace("**/", ""))
        ):
            return False
        if rule.domain_glob and not fnmatch.fnmatch(domain, rule.domain_glob):
            return False
        if rule.mcp_tool_glob and not fnmatch.fnmatch(mcp_tool, rule.mcp_tool_glob):
            return False
        # category-only rule
        if not any(
            [rule.command_glob, rule.path_glob, rule.domain_glob, rule.mcp_tool_glob, rule.risk]
        ) and rule.category:
            return rule.category == category
        if rule.command_glob or rule.path_glob or rule.domain_glob or rule.mcp_tool_glob:
            return True
        return bool(rule.category)
