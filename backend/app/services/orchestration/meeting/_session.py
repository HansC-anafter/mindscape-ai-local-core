"""Compatibility entrypoint for meeting session lifecycle helpers."""

from backend.app.services.orchestration.meeting.session_core.lifecycle_mixin import (
    MeetingSessionLifecycleMixin,
)
from backend.app.services.orchestration.meeting.session_core.memory_trace_mixin import (
    MeetingSessionMemoryTraceMixin,
)
from backend.app.services.orchestration.meeting.session_core.playbook_discovery_mixin import (
    MeetingSessionPlaybookDiscoveryMixin,
)
from backend.app.services.orchestration.meeting.session_core.workspace_metadata_mixin import (
    MeetingSessionWorkspaceMetadataMixin,
)


class MeetingSessionMixin(
    MeetingSessionWorkspaceMetadataMixin,
    MeetingSessionMemoryTraceMixin,
    MeetingSessionLifecycleMixin,
    MeetingSessionPlaybookDiscoveryMixin,
):
    """Mixin providing session lifecycle methods for MeetingEngine."""
