"""Compatibility entrypoint for meeting action item helpers."""

from backend.app.services.orchestration.meeting.action_items_core import (
    MeetingActionItemsMixin,
)

__all__ = ["MeetingActionItemsMixin"]
