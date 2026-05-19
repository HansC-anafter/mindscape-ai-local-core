"""Modular action item helpers for MeetingEngine."""

from backend.app.services.orchestration.meeting.action_items_core.builder_mixin import (
    ActionItemBuilderMixin,
)
from backend.app.services.orchestration.meeting.action_items_core.native_spatial_mixin import (
    NativeSpatialActionItemsMixin,
)
from backend.app.services.orchestration.meeting.action_items_core.parser_mixin import (
    ActionItemParserMixin,
)
from backend.app.services.orchestration.meeting.action_items_core.task_projection_mixin import (
    ActionItemTaskProjectionMixin,
)


class MeetingActionItemsMixin(
    NativeSpatialActionItemsMixin,
    ActionItemBuilderMixin,
    ActionItemTaskProjectionMixin,
    ActionItemParserMixin,
):
    """Mixin providing action item methods for MeetingEngine."""


__all__ = ["MeetingActionItemsMixin"]
