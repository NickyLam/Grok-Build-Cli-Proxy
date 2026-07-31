from __future__ import annotations

from enum import StrEnum

from grok_proxy.errors import ProxyError


class ResponseStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INCOMPLETE = "incomplete"


TERMINAL_STATUSES: frozenset[ResponseStatus] = frozenset(
    {
        ResponseStatus.COMPLETED,
        ResponseStatus.FAILED,
        ResponseStatus.CANCELLED,
        ResponseStatus.INCOMPLETE,
    }
)

# from -> allowed targets
_TRANSITIONS: dict[ResponseStatus, frozenset[ResponseStatus]] = {
    ResponseStatus.QUEUED: frozenset(
        {
            ResponseStatus.IN_PROGRESS,
            ResponseStatus.CANCELLED,
            ResponseStatus.FAILED,
        }
    ),
    ResponseStatus.IN_PROGRESS: frozenset(
        {
            ResponseStatus.WAITING_FOR_APPROVAL,
            ResponseStatus.COMPLETED,
            ResponseStatus.FAILED,
            ResponseStatus.CANCELLED,
            ResponseStatus.INCOMPLETE,
        }
    ),
    ResponseStatus.WAITING_FOR_APPROVAL: frozenset(
        {
            ResponseStatus.IN_PROGRESS,
            ResponseStatus.FAILED,
            ResponseStatus.CANCELLED,
            ResponseStatus.INCOMPLETE,
        }
    ),
    ResponseStatus.COMPLETED: frozenset(),
    ResponseStatus.FAILED: frozenset(),
    ResponseStatus.CANCELLED: frozenset(),
    ResponseStatus.INCOMPLETE: frozenset(),
}


class ResponseStateMachine:
    """Strict Response status transitions."""

    def __init__(self, status: ResponseStatus | str = ResponseStatus.QUEUED) -> None:
        self._status = ResponseStatus(status)

    @property
    def status(self) -> ResponseStatus:
        return self._status

    @property
    def is_terminal(self) -> bool:
        return self._status in TERMINAL_STATUSES

    def can_transition(self, target: ResponseStatus | str) -> bool:
        target_status = ResponseStatus(target)
        if target_status == self._status:
            # cancel is idempotent when already cancelled
            return target_status == ResponseStatus.CANCELLED
        return target_status in _TRANSITIONS.get(self._status, frozenset())

    def transition(self, target: ResponseStatus | str) -> ResponseStatus:
        target_status = ResponseStatus(target)
        if target_status == self._status and target_status == ResponseStatus.CANCELLED:
            return self._status
        if not self.can_transition(target_status):
            raise ProxyError(
                f"Illegal response status transition: {self._status.value} -> {target_status.value}",
                status_code=409,
                code="illegal_status_transition",
                details={"from": self._status.value, "to": target_status.value},
            )
        self._status = target_status
        return self._status

    def assert_waiting_for_approval(self, *, has_pending_permission: bool) -> None:
        if self._status == ResponseStatus.WAITING_FOR_APPROVAL and not has_pending_permission:
            raise ProxyError(
                "waiting_for_approval requires at least one pending permission",
                status_code=500,
                code="invalid_waiting_state",
            )
