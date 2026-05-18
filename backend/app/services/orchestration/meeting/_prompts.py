"""Compatibility entrypoint for meeting prompt construction."""

from backend.app.services.orchestration.meeting.prompt_core.context_bridge_mixin import (
    MeetingPromptContextBridgeMixin,
)
from backend.app.services.orchestration.meeting.prompt_core.native_spatial_mixin import (
    MeetingPromptNativeSpatialMixin,
)
from backend.app.services.orchestration.meeting.prompt_core.output_mixin import (
    MeetingPromptOutputMixin,
)
from backend.app.services.orchestration.meeting.prompt_core.tool_inventory_mixin import (
    MeetingPromptToolInventoryMixin,
)
from backend.app.services.orchestration.meeting.prompt_core.turn_prompt_mixin import (
    MeetingPromptTurnMixin,
)


class MeetingPromptsMixin(
    MeetingPromptNativeSpatialMixin,
    MeetingPromptToolInventoryMixin,
    MeetingPromptContextBridgeMixin,
    MeetingPromptTurnMixin,
    MeetingPromptOutputMixin,
):
    """Mixin providing prompt construction methods for MeetingEngine."""
