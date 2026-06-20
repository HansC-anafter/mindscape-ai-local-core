"""Compile request-contract data intents into a deterministic planner tool plan."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.app.services.orchestration.meeting.role_profiles import (
    MeetingRoleProfileResolver,
)
from backend.app.services.orchestration.meeting.planner_contract_execution.manifest_registry import (
    PlannerContractManifestRegistry,
)
from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_creative_space_lane import (
    CreativeSpacePlannerLaneCompiler,
)
from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_declarative_lane import (
    DeclarativePlannerLaneCompiler,
)
from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_models import (
    PlannerToolPlan,
)


class PlannerToolPlanCompiler:
    """Build one MeetingEngine-scoped tool plan from installed planner contracts."""

    def __init__(
        self,
        registry: Optional[PlannerContractManifestRegistry] = None,
        role_profile_resolver: Optional[MeetingRoleProfileResolver] = None,
    ) -> None:
        self.registry = registry or PlannerContractManifestRegistry()
        self.role_profile_resolver = role_profile_resolver or MeetingRoleProfileResolver()

    def compile(
        self,
        *,
        request_contract: Optional[Any],
        session_metadata: Optional[Dict[str, Any]],
        workspace_id: str,
        meeting_id: str,
    ) -> Optional[PlannerToolPlan]:
        """Return a complete executable plan, or None when the contract is out of scope."""
        metadata = session_metadata if isinstance(session_metadata, dict) else {}
        pack_id = self.registry.active_pack_id(metadata)
        if not pack_id:
            return None

        declarative_plan = DeclarativePlannerLaneCompiler(
            registry=self.registry,
            role_profile_resolver=self.role_profile_resolver,
        ).compile_if_enabled(
            request_contract=request_contract,
            session_metadata=metadata,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            pack_id=pack_id,
        )
        if declarative_plan is not None:
            return declarative_plan

        return CreativeSpacePlannerLaneCompiler(self.registry).compile(
            request_contract=request_contract,
            session_metadata=metadata,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            pack_id=pack_id,
        )
