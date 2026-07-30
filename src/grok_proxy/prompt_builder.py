from __future__ import annotations

from grok_proxy.errors import ProxyError
from grok_proxy.models import ChatMessage


def _format_message(msg: ChatMessage) -> str:
    text = msg.text_content().strip()
    role = msg.role.strip().lower()
    if role == "system":
        return text
    if role == "user":
        return f"User: {text}" if text else "User:"
    if role == "assistant":
        return f"Assistant: {text}" if text else "Assistant:"
    if role == "tool":
        name = msg.name or "tool"
        return f"Tool({name}): {text}"
    return f"{msg.role}: {text}"


def extract_system_rules(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
    """Pull leading system messages into optional --rules text; return rest."""
    rules_parts: list[str] = []
    rest: list[ChatMessage] = []
    i = 0
    while i < len(messages) and messages[i].role.strip().lower() == "system":
        t = messages[i].text_content().strip()
        if t:
            rules_parts.append(t)
        i += 1
    rest = messages[i:]
    # Also fold mid-conversation system messages into rest linearization
    rules = "\n\n".join(rules_parts) if rules_parts else None
    return rules, rest


def build_prompt(
    messages: list[ChatMessage],
    *,
    session_id: str | None,
) -> tuple[str, str | None]:
    """
    Build headless prompt and optional rules string.

    Returns:
        (prompt, rules_from_system)
    """
    if not messages:
        raise ProxyError("messages must not be empty", status_code=400, code="empty_messages")

    if session_id:
        # Resume: only last user turn; optional preceding system as prompt prefix
        last = messages[-1]
        if last.role.strip().lower() != "user":
            raise ProxyError(
                "When session_id is set, the last message must be role=user "
                "(Grok session already holds prior turns).",
                status_code=400,
                code="resume_requires_user_message",
            )
        # Collect trailing system messages immediately before last user? Prefer only last user.
        # If there are system messages in this request after history, prefix them.
        prefix_systems = [
            m.text_content().strip()
            for m in messages[:-1]
            if m.role.strip().lower() == "system" and m.text_content().strip()
        ]
        user_text = last.text_content()
        if prefix_systems:
            prompt = "\n\n".join(prefix_systems) + "\n\n" + user_text
        else:
            prompt = user_text
        if not prompt.strip():
            raise ProxyError("User message content is empty", status_code=400, code="empty_prompt")
        return prompt, None

    rules, rest = extract_system_rules(messages)
    if not rest:
        # Only system messages — use them as the prompt
        if rules:
            return rules, None
        raise ProxyError("No user/assistant content in messages", status_code=400, code="empty_prompt")

    # Single user message with no prior turns: raw content (no "User:" prefix)
    if len(rest) == 1 and rest[0].role.strip().lower() == "user":
        prompt = rest[0].text_content()
    else:
        parts = [_format_message(m) for m in rest]
        prompt = "\n\n".join(p for p in parts if p is not None)
        if not prompt.endswith("\n") and rest[-1].role.strip().lower() == "user":
            # Encourage continuation as assistant for multi-turn dumps
            pass

    if not prompt.strip():
        raise ProxyError("Resolved prompt is empty", status_code=400, code="empty_prompt")
    return prompt, rules
