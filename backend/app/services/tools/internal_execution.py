"""Process-local authority proving execution came from a claimed runner task."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class InternalToolExecutionAuthority:
    task_id: str
    tool_name: str
    admission_snapshot_hash: str


_ACTIVE_INTERNAL_TOOL_AUTHORITY: ContextVar[
    InternalToolExecutionAuthority | None
] = ContextVar(
    "active_internal_tool_execution_authority",
    default=None,
)


@contextmanager
def runner_internal_tool_authority(
    *,
    task_id: str,
    tool_name: str,
    admission_snapshot_hash: str,
) -> Iterator[InternalToolExecutionAuthority]:
    authority = InternalToolExecutionAuthority(
        task_id=str(task_id or "").strip(),
        tool_name=str(tool_name or "").strip(),
        admission_snapshot_hash=str(admission_snapshot_hash or "").strip(),
    )
    if (
        not authority.task_id
        or not authority.tool_name
        or len(authority.admission_snapshot_hash) != 64
    ):
        raise ValueError("internal_tool_runner_authority_invalid")
    token = _ACTIVE_INTERNAL_TOOL_AUTHORITY.set(authority)
    try:
        yield authority
    finally:
        _ACTIVE_INTERNAL_TOOL_AUTHORITY.reset(token)


def require_internal_tool_authority(
    *,
    task_id: str,
    tool_name: str,
) -> InternalToolExecutionAuthority:
    authority = _ACTIVE_INTERNAL_TOOL_AUTHORITY.get()
    if (
        authority is None
        or authority.task_id != str(task_id or "").strip()
        or authority.tool_name != str(tool_name or "").strip()
    ):
        raise PermissionError("runner_internal_tool_authority_required")
    return authority


__all__ = [
    "InternalToolExecutionAuthority",
    "require_internal_tool_authority",
    "runner_internal_tool_authority",
]
