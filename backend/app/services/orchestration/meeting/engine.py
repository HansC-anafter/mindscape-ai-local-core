"""Meeting Engine compatibility entrypoint."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.meeting._action_items import (
    MeetingActionItemsMixin,
)
from backend.app.services.orchestration.meeting._dispatch import (
    MeetingDispatchMixin,
)
from backend.app.services.orchestration.meeting._events import (
    MeetingEventsMixin,
)
from backend.app.services.orchestration.meeting._generation import (
    MeetingGenerationMixin,
)
from backend.app.services.orchestration.meeting._governance import (
    MeetingGovernanceMixin,
)
from backend.app.services.orchestration.meeting._ir_compiler import (
    MeetingIRCompilerMixin,
)
from backend.app.services.orchestration.meeting._l2_bridge import (
    MeetingL2BridgeMixin,
)
from backend.app.services.orchestration.meeting._prompts import (
    MeetingPromptsMixin,
)
from backend.app.services.orchestration.meeting._session import (
    MeetingSessionMixin,
)
from backend.app.services.orchestration.meeting._tool_discovery import (
    MeetingToolDiscoveryMixin,
)
from backend.app.services.orchestration.meeting.engine_core.bootstrap_mixin import (
    MeetingEngineBootstrapMixin,
)
from backend.app.services.orchestration.meeting.engine_core.deliberation_mixin import (
    MeetingEngineDeliberationMixin,
)
from backend.app.services.orchestration.meeting.engine_core.direct_dispatch_mixin import (
    MeetingEngineDirectDispatchMixin,
)
from backend.app.services.orchestration.meeting.engine_core.fallback_deliverable_mixin import (
    MeetingEngineFallbackDeliverableMixin,
)
from backend.app.services.orchestration.meeting.engine_core.grounded_answer_mixin import (
    MeetingEngineGroundedAnswerMixin,
)
from backend.app.services.orchestration.meeting.engine_core.lifecycle_mixin import (
    MeetingEngineLifecycleMixin,
)
from backend.app.services.orchestration.meeting.engine_core.pipeline_stages_mixin import (
    MeetingEnginePipelineStagesMixin,
)
from backend.app.services.orchestration.meeting.engine_core.playbook_defaults_mixin import (
    MeetingEnginePlaybookDefaultsMixin,
)
from backend.app.services.orchestration.meeting.engine_core.playbook_requests_mixin import (
    MeetingEnginePlaybookRequestsMixin,
)
from backend.app.services.orchestration.meeting.engine_core.request_contract_mixin import (
    MeetingEngineRequestContractMixin,
)


@dataclass
class RoleTurnResult:
    """Result of a single deliberation role turn in a meeting round."""

    role_id: str
    role_name: str
    round_number: int
    content: str
    converged: bool = False


@dataclass
class MeetingResult:
    """Final output of a completed meeting session."""

    session_id: str
    minutes_md: str
    decision: str
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
    task_ir: Optional[Any] = None
    dispatch_result: Optional[Dict[str, Any]] = None
    completion_status: str = "accepted"
    grounded_answer_receipt: Optional[Dict[str, Any]] = None


class MeetingEngine(
    MeetingEngineBootstrapMixin,
    MeetingEngineLifecycleMixin,
    MeetingEngineGroundedAnswerMixin,
    MeetingEngineDirectDispatchMixin,
    MeetingEnginePipelineStagesMixin,
    MeetingEngineDeliberationMixin,
    MeetingEngineRequestContractMixin,
    MeetingEnginePlaybookRequestsMixin,
    MeetingEnginePlaybookDefaultsMixin,
    MeetingEngineFallbackDeliverableMixin,
    MeetingEventsMixin,
    MeetingGovernanceMixin,
    MeetingPromptsMixin,
    MeetingActionItemsMixin,
    MeetingGenerationMixin,
    MeetingIRCompilerMixin,
    MeetingDispatchMixin,
    MeetingL2BridgeMixin,
    MeetingSessionMixin,
    MeetingToolDiscoveryMixin,
):
    """Drives a bounded multi-role meeting with real LLM turns and action landing."""

    @staticmethod
    def _meeting_result_class():
        return MeetingResult

    @staticmethod
    def _role_turn_result_class():
        return RoleTurnResult
