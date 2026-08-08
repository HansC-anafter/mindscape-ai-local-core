"""Canonical Meeting adapter for admitted knowledge_query tool execution."""

from __future__ import annotations

from typing import Any

from backend.app.services.orchestration.meeting.meeting_command_authority import (
    MeetingCommandAuthority,
)
from backend.app.services.unified_tool_executor import UnifiedToolExecutor
from backend.app.services.unified_tool_executor_core.governance_context import (
    build_verified_tool_execution_context,
)
from backend.app.services.workspace_capability_admission import (
    RootAdmissionRequest,
    WorkspaceCapabilityAdmissionFacade,
)

from .contracts import GroundedKnowledgeAnswerOperation


class MeetingKnowledgeQueryPort:
    """Execute knowledge_query only through root admission and unified tools."""

    def __init__(
        self,
        *,
        admission_facade: WorkspaceCapabilityAdmissionFacade | None = None,
        executor: UnifiedToolExecutor | None = None,
    ) -> None:
        self._admission_facade = (
            admission_facade or WorkspaceCapabilityAdmissionFacade()
        )
        self._executor = executor or UnifiedToolExecutor()

    async def execute(
        self,
        operation: GroundedKnowledgeAnswerOperation,
        *,
        authority: MeetingCommandAuthority,
    ) -> dict[str, Any]:
        admission = await self._admission_facade.admit_root(
            RootAdmissionRequest(
                workspace_id=authority.workspace_id,
                explicit_active_group_id=authority.active_group_id,
                product_surface_id=(
                    "psc.local-core.retrievable-knowledge-projection-"
                    "and-agentic-query.v1"
                ),
                selector_kind="tool",
                selector_key="knowledge_query",
                operation_type="read",
                entry="local",
                execution_backend="local",
                actor_user_id=authority.actor_user_id,
                allowed_workspace_ids=list(
                    authority.allowed_workspace_ids
                ),
                allowed_group_ids=list(authority.allowed_group_ids),
                trace_id=authority.trace_id,
                root_execution_id=authority.root_execution_id,
            )
        )
        governed_arguments = {
            **operation.model_dump(mode="json"),
            "execution_admission_snapshot": admission.snapshot.model_dump(
                mode="json"
            ),
            "root_execution_id": authority.root_execution_id,
        }
        result = await self._executor.execute_tool(
            tool_name="knowledge_query",
            arguments=governed_arguments,
            timeout=30.0,
            governance_context=build_verified_tool_execution_context(
                admission
            ),
        )
        if not result.success or not isinstance(result.result, dict):
            raise RuntimeError(
                str(result.error or "meeting_knowledge_query_failed")
            )
        return {
            **result.result,
            "_meeting_admission_snapshot_hash": (
                admission.snapshot.snapshot_hash
            ),
        }


__all__ = ["MeetingKnowledgeQueryPort"]
