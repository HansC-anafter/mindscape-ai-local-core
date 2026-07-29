"""
Dashboard Aggregator service
Responsible for aggregating data from Local-Core tables to Dashboard DTOs
"""

import asyncio
import logging
from typing import Optional, List
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from ..models.dashboard import (
    DashboardSummaryDTO,
    DashboardCountsDTO,
    InboxItemDTO,
    CaseCardDTO,
    AssignmentCardDTO,
    WorkspaceCardDTO,
    PaginatedResponse,
    DashboardQuery,
    WorkspaceSetupStatus,
    SetupItem,
)
from ..models.workspace import WorkspaceType
from ..dependencies.auth import AuthContext
from ..utils.scope import ParsedScope
from ..services.mindscape_store import MindscapeStore
from .dashboard_workload_query_service import DashboardWorkloadQueryService
from .dashboard_mappings import (
    map_execution_to_case,
)

logger = logging.getLogger(__name__)


class DashboardAggregator:
    """Dashboard data aggregation service"""

    # Unsupported count fields (populated in Summary.not_supported)
    NOT_SUPPORTED_COUNTS = [
        "mentions",
        "delegated_pending",
        "overdue_items",
        "open_assignments",
    ]

    def __init__(
        self,
        store: MindscapeStore,
        *,
        workload_query_service: DashboardWorkloadQueryService | None = None,
    ):
        self.store = store
        self.executions_store = store.playbook_executions
        self.workload_query_service = (
            workload_query_service or DashboardWorkloadQueryService()
        )

    async def get_summary(
        self,
        auth: AuthContext,
        query: DashboardQuery,
        effective_scope: ParsedScope,
    ) -> DashboardSummaryDTO:
        """
        Get dashboard summary

        Args:
            auth: Authentication context
            query: Query parameters
            effective_scope: Validated effective scope (may be downgraded from group to global)
        """
        # Determine workspace range based on effective_scope
        workspace_ids = self._get_workspace_ids_for_scope(auth, effective_scope)

        # Calculate counts
        counts = await self._calculate_counts(workspace_ids)

        # Calculate needs_setup
        needs_setup = await self._calculate_needs_setup(workspace_ids)

        # Collect warnings
        warnings = effective_scope.warnings.copy()
        warnings.append(
            "open_assignments not supported in Local-Core "
            "(runtime tasks are not user assignments)"
        )

        return DashboardSummaryDTO(
            scope=(
                f"{effective_scope.type}:{effective_scope.id}"
                if effective_scope.id
                else effective_scope.type
            ),
            counts=counts,
            recent_activity_at=_utc_now(),
            needs_setup=needs_setup,
            not_supported=self.NOT_SUPPORTED_COUNTS,
            warnings=warnings,
        )

    async def get_inbox(
        self,
        auth: AuthContext,
        query: DashboardQuery,
        effective_scope: ParsedScope,
    ) -> PaginatedResponse[InboxItemDTO]:
        """
        Get inbox items

        Sorting rules (cloud specification):
        1. pending_decision (tier 1) - NOT SUPPORTED in Local-Core
        2. assignment (tier 2) - NOT SUPPORTED in Local-Core
        3. mention (tier 3) - NOT SUPPORTED in Local-Core
        4. delegated_pending (tier 4) - NOT SUPPORTED in Local-Core
        5. system_alert (tier 5) - PARTIALLY SUPPORTED (needs_setup)
        6. case_update (tier 6) - PARTIALLY SUPPORTED (execution status changes)

        Within same tier: due_at ascending (None last), created_at descending
        """
        # Add system_alert items (tier 5) from needs_setup
        # Local-Core: system_alert items represent workspaces that need setup
        # Note: Currently _calculate_needs_setup returns empty list
        # When implemented, it should return SetupItem enum values, and we can create alerts
        # For now, system_alert items are not generated.

        # Collect warnings about unsupported inbox types
        # NOTE: Local-Core does not generate items for these types:
        # - pending_decision (tier 1): No decision table exists
        # - assignment (tier 2): Runtime tasks are not user assignments
        # - mention (tier 3): No mention table exists
        # - delegated_pending (tier 4): No delegation flow exists
        # - system_alert (tier 5): Partially supported (only workspace setup, currently empty)
        # - case_update (tier 6): Not implemented (execution status changes could be tracked)
        unsupported_warnings = [
            "pending_decision items not generated in Local-Core (no decision table)",
            "mention items not generated in Local-Core (no mention table)",
            "assignment items not generated in Local-Core (runtime tasks are not user assignments)",
            "needs_changes items not generated in Local-Core (assignment has no review_status)",
            "delegated_pending items not generated in Local-Core (no delegation flow)",
            "system_alert items partially supported (only workspace setup alerts, currently none generated)",
            "case_update items not implemented (execution status changes not tracked as inbox items)",
        ]

        return PaginatedResponse(
            items=[],
            total=0,
            limit=query.limit,
            offset=query.offset,
            has_more=False,
            warnings=effective_scope.warnings + unsupported_warnings,
        )

    async def get_cases(
        self,
        auth: AuthContext,
        query: DashboardQuery,
        effective_scope: ParsedScope,
    ) -> PaginatedResponse[CaseCardDTO]:
        """Get Case card list"""
        workspace_ids = self._get_workspace_ids_for_scope(auth, effective_scope)
        cases: List[CaseCardDTO] = []

        for ws_id in workspace_ids:
            workspace = await self.store.get_workspace(ws_id)
            if not workspace:
                continue

            executions = await asyncio.to_thread(
                self.executions_store.list_executions_by_workspace,
                ws_id,
                100,
            )
            for exec in executions:
                case_data = map_execution_to_case(
                    execution=exec.__dict__,
                    workspace_id=ws_id,
                    workspace_name=workspace.title,
                    owner_user_id=auth.user_id,
                )
                cases.append(CaseCardDTO(**case_data))

        # Sort: blocked > open, updated_at desc
        cases.sort(
            key=lambda c: (
                0 if c.status == "blocked" else 1,
                -c.updated_at.timestamp() if c.updated_at else 0,
            )
        )

        total = len(cases)
        cases = cases[query.offset : query.offset + query.limit]

        return PaginatedResponse(
            items=cases,
            total=total,
            limit=query.limit,
            offset=query.offset,
            has_more=query.offset + len(cases) < total,
            warnings=effective_scope.warnings,
        )

    async def get_assignments(
        self,
        auth: AuthContext,
        query: DashboardQuery,
        effective_scope: ParsedScope,
    ) -> PaginatedResponse[AssignmentCardDTO]:
        """Get Assignment card list"""
        return PaginatedResponse(
            items=[],
            total=0,
            limit=query.limit,
            offset=query.offset,
            has_more=False,
            warnings=effective_scope.warnings
            + [
                "assignments not supported in Local-Core (runtime tasks are not user assignments)",
                "review_status not supported in Local-Core",
                "due_at not supported in Local-Core",
            ],
        )

    # ==================== Private Methods ====================

    def _get_workspace_ids_for_scope(
        self,
        auth: AuthContext,
        scope: ParsedScope,
    ) -> List[str]:
        """Determine workspace range based on scope"""
        if scope.type == "global":
            return auth.workspace_ids
        elif scope.type == "workspace":
            # Return only this workspace (permission already validated in validate_scope)
            return [scope.id] if scope.id else []
        else:
            # group scope should have been downgraded to global
            return auth.workspace_ids

    async def _calculate_counts(self, workspace_ids: List[str]) -> DashboardCountsDTO:
        """
        Calculate count statistics

        NOTE: Local-Core limitations (these counts are always 0):
        - pending_decisions: Always 0 (no decision table exists)
        - open_assignments: Always 0 (runtime tasks are not user assignments)
        - mentions: Always 0 (no mention table exists)
        - delegated_pending: Always 0 (no delegation flow exists)
        - overdue_items: Always 0 (tasks table has no due_at field)

        These limitations are documented in DashboardSummaryDTO.not_supported
        and DashboardSummaryDTO.warnings fields.
        """
        return await self.workload_query_service.load_counts(
            workspace_ids,
        )

    async def _calculate_needs_setup(self, workspace_ids: List[str]) -> List[SetupItem]:
        """Calculate setup requirements"""
        # Simplified: return empty list, can be extended in the future
        return []

    async def get_workspaces(
        self,
        auth: AuthContext,
        query: DashboardQuery,
        search: Optional[str] = None,
        setup_status: Optional[WorkspaceSetupStatus] = None,
        pinned_only: bool = False,
    ) -> PaginatedResponse[WorkspaceCardDTO]:
        """
        Get Workspace card list

        NOTE: Limitations in Local-Core:
        - pinned_only: Parameter exists but workspace pinning is not implemented
          (all workspaces are treated as unpinned)
        - setup_status: Filtering by setup status is partially supported
          (only WorkspaceSetupStatus.READY vs NEEDS_SETUP, others may not work)
        """
        workspace_ids = auth.workspace_ids
        workspaces: List[WorkspaceCardDTO] = []

        for ws_id in workspace_ids:
            workspace = await self.store.get_workspace(ws_id)
            if not workspace:
                continue

            # Apply search filter
            if search and search.lower() not in (workspace.title or "").lower():
                if not (
                    workspace.description
                    and search.lower() in workspace.description.lower()
                ):
                    continue

            # NOTE: pinned_only filter is not implemented (workspace pinning not supported)
            # All workspaces are treated as unpinned, so pinned_only=True will return empty list
            if pinned_only:
                continue  # Skip all workspaces since pinning is not implemented

            # Get workspace statistics
            executions = await asyncio.to_thread(
                self.executions_store.list_executions_by_workspace,
                ws_id,
                100,
            )
            open_cases = sum(1 for e in executions if e.status == "running")
            running_jobs = open_cases
            pending_decisions = 0  # Local-Core does not support decisions

            # Determine setup status
            ws_setup_status = WorkspaceSetupStatus.READY
            needs_setup_items: List[SetupItem] = []

            # Create workspace card
            workspace_card = WorkspaceCardDTO(
                id=workspace.id,
                name=workspace.title,
                description=workspace.description,
                setup_status=ws_setup_status,
                needs_setup_items=needs_setup_items,
                boundary_type="personal",
                open_cases_count=open_cases,
                pending_decisions_count=pending_decisions,
                running_jobs_count=running_jobs,
                last_activity_at=(
                    workspace.updated_at if hasattr(workspace, "updated_at") else None
                ),
                last_activity_type=None,
                members_count=1,
                current_user_role="owner",
                is_pinned=False,
                tags=[],
                primary_action=None,
                created_at=(
                    workspace.created_at
                    if hasattr(workspace, "created_at")
                    else _utc_now()
                ),
                updated_at=(
                    workspace.updated_at
                    if hasattr(workspace, "updated_at")
                    else _utc_now()
                ),
            )

            # Apply setup_status filter
            if setup_status and workspace_card.setup_status != setup_status:
                continue

            # Apply pinned_only filter
            if pinned_only and not workspace_card.is_pinned:
                continue

            workspaces.append(workspace_card)

        # Sort by last_activity_at descending
        workspaces.sort(
            key=lambda w: w.last_activity_at.timestamp() if w.last_activity_at else 0,
            reverse=True,
        )

        total = len(workspaces)
        workspaces = workspaces[query.offset : query.offset + query.limit]

        return PaginatedResponse(
            items=workspaces,
            total=total,
            limit=query.limit,
            offset=query.offset,
            has_more=query.offset + len(workspaces) < total,
            warnings=[],
        )
