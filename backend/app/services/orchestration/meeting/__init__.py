"""
Meeting engine package.

Public API re-exports for backward compatibility.
"""

from typing import Any

__all__ = [
    "RoleTurnResult",
    "MeetingEngine",
    "MeetingResult",
]


def __getattr__(name: str) -> Any:
    if name in {"RoleTurnResult", "MeetingEngine", "MeetingResult"}:
        from backend.app.services.orchestration.meeting.engine import (
            MeetingEngine,
            MeetingResult,
            RoleTurnResult,
        )

        exports = {
            "RoleTurnResult": RoleTurnResult,
            "MeetingEngine": MeetingEngine,
            "MeetingResult": MeetingResult,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
