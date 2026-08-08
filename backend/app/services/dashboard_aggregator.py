"""Aggregate bounded Local Core data into Dashboard DTOs."""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from ..dependencies.auth import AuthContext
from ..models.dashboard import (
    AssignmentCardDTO,
    CaseCardDTO,
    DashboardCountsDTO,
    DashboardQuery,
    DashboardSummaryDTO,
    InboxItemDTO,
    InboxItemType,
    PaginatedResponse,
    SetupItem,
    WorkspaceCardDTO,
    WorkspaceSetupStatus,
)
from ..services.mindscape_store import MindscapeStore
from ..utils.scope import ParsedScope
from .dashboard_mappings import map_execution_to_case, map_task_to_assignment
from .stores.postgres.dashboard_read_store import DashboardReadStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DashboardAggregator:
    """Dashboard data aggregation service."""

    NOT_SUPPORTED_COUNTS = [
        "mentions",
        "delegated_pending",
        "overdue_items",
    ]

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.dashboard = DashboardReadStore()

    async def get_summary(
        self,
        auth: AuthContext,
        query: DashboardQuery,
        effective_scope: ParsedScope,
    ) -> DashboardSummaryDTO:
        workspace_ids = self._get_workspace_ids_for_scope(auth, effective_scope)
        raw_counts = await asyncio.to_thread(
            self.dashboard.get_summary_counts,
            workspace_ids,
        )
        counts = DashboardCountsDTO(
            pending_decisions=0,
            open_assignments=raw_counts["open_assignments"],
            open_cases=raw_counts["open_cases"],
            blocked_cases=raw_counts["blocked_cases"],
            running_jobs=raw_counts["running_jobs"],
            overdue_items=0,
            mentions=0,
            delegated_pending=0,
        )
        return DashboardSummaryDTO(
            scope=(
                f"{effective_scope.type}:{effective_scope.id}"
                if effective_scope.id
                else effective_scope.type
            ),
            counts=counts,
            recent_activity_at=_utc_now(),
            needs_setup=[],
            not_supported=self.NOT_SUPPORTED_COUNTS,
            warnings=effective_scope.warnings.copy(),
        )

    async def get_inbox(
        self,
        auth: AuthContext,
        query: DashboardQuery,
        effective_scope: ParsedScope,
    ) -> PaginatedResponse[InboxItemDTO]:
        workspace_ids = self._get_workspace_ids_for_scope(auth, effective_scope)
        tasks, total = await asyncio.to_thread(
            self.dashboard.list_inbox_page,
            workspace_ids,
            limit=query.limit,
            offset=query.offset,
        )
        items = [self._task_to_inbox_item(task) for task in tasks]
        unsupported_warnings = [
            "pending_decision items not generated in Local-Core (no decision table)",
            "mention items not generated in Local-Core (no mention table)",
            "needs_changes items not generated in Local-Core (assignment has no review_status)",
            "delegated_pending items not generated in Local-Core (no delegation flow)",
            "system_alert items partially supported (only workspace setup alerts, currently none generated)",
            "case_update items not implemented (execution status changes not tracked as inbox items)",
        ]
        return PaginatedResponse(
            items=items,
            total=total,
            limit=query.limit,
            offset=query.offset,
            has_more=query.offset + len(items) < total,
            warnings=effective_scope.warnings + unsupported_warnings,
        )

    async def get_cases(
        self,
        auth: AuthContext,
        query: DashboardQuery,
        effective_scope: ParsedScope,
    ) -> PaginatedResponse[CaseCardDTO]:
        workspace_ids = self._get_workspace_ids_for_scope(auth, effective_scope)
        rows, total = await asyncio.to_thread(
            self.dashboard.list_case_page,
            workspace_ids,
            limit=query.limit,
            offset=query.offset,
        )
        cases = [
            CaseCardDTO(
                **map_execution_to_case(
                    execution=row,
                    workspace_id=row["workspace_id"],
                    workspace_name=row["workspace_name"],
                    owner_user_id=auth.user_id,
                    tasks_count=row["tasks_count"],
                )
            )
            for row in rows
        ]
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
        workspace_ids = self._get_workspace_ids_for_scope(auth, effective_scope)
        rows, total = await asyncio.to_thread(
            self.dashboard.list_assignment_page,
            workspace_ids,
            limit=query.limit,
            offset=query.offset,
        )
        assignments = [
            AssignmentCardDTO(
                **map_task_to_assignment(
                    task=row,
                    workspace_id=row["workspace_id"],
                    workspace_name=row["workspace_name"],
                    owner_user_id=auth.user_id,
                )
            )
            for row in rows
        ]
        warnings = effective_scope.warnings
        if assignments:
            warnings = warnings + [
                "review_status not supported in Local-Core",
                "due_at not supported in Local-Core",
            ]
        return PaginatedResponse(
            items=assignments,
            total=total,
            limit=query.limit,
            offset=query.offset,
            has_more=query.offset + len(assignments) < total,
            warnings=warnings,
        )

    async def get_workspaces(
        self,
        auth: AuthContext,
        query: DashboardQuery,
        search: Optional[str] = None,
        setup_status: Optional[WorkspaceSetupStatus] = None,
        pinned_only: bool = False,
    ) -> PaginatedResponse[WorkspaceCardDTO]:
        if pinned_only or (
            setup_status is not None and setup_status != WorkspaceSetupStatus.READY
        ):
            return self._empty_workspace_page(query)

        rows, total = await asyncio.to_thread(
            self.dashboard.list_workspace_page,
            auth.workspace_ids,
            search=search,
            limit=query.limit,
            offset=query.offset,
        )
        workspaces = [self._workspace_to_card(row) for row in rows]
        return PaginatedResponse(
            items=workspaces,
            total=total,
            limit=query.limit,
            offset=query.offset,
            has_more=query.offset + len(workspaces) < total,
            warnings=[],
        )

    def _get_workspace_ids_for_scope(
        self,
        auth: AuthContext,
        scope: ParsedScope,
    ) -> List[str]:
        if scope.type == "workspace":
            return [scope.id] if scope.id else []
        return auth.workspace_ids

    @staticmethod
    def _task_to_inbox_item(task: dict) -> InboxItemDTO:
        return InboxItemDTO(
            id=task["task_id"],
            item_type=InboxItemType.ASSIGNMENT,
            source_type="task",
            source_id=task["task_id"],
            workspace_id=task["workspace_id"],
            workspace_name=None,
            case_id=task["execution_id"],
            case_title=task["pack_id"],
            thread_id=None,
            title=task["task_type"],
            summary=task["description"],
            status=task["status"],
            priority=0,
            is_overdue=False,
            due_at=None,
            assignee_user_id=None,
            assignee_name=None,
            created_by_user_id=None,
            created_by_name=None,
            available_actions=["view_detail"],
            extra={},
            created_at=task["created_at"],
            updated_at=task["started_at"] or task["updated_at"] or task["created_at"],
        )

    @staticmethod
    def _workspace_to_card(workspace: dict) -> WorkspaceCardDTO:
        created_at = workspace["created_at"] or _utc_now()
        updated_at = workspace["updated_at"] or _utc_now()
        open_cases = int(workspace["open_cases"] or 0)
        return WorkspaceCardDTO(
            id=workspace["id"],
            name=workspace["title"],
            description=workspace["description"],
            setup_status=WorkspaceSetupStatus.READY,
            needs_setup_items=[],
            boundary_type="personal",
            open_cases_count=open_cases,
            pending_decisions_count=0,
            running_jobs_count=open_cases,
            last_activity_at=workspace["updated_at"],
            last_activity_type=None,
            members_count=1,
            current_user_role="owner",
            is_pinned=False,
            tags=[],
            primary_action=None,
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _empty_workspace_page(
        query: DashboardQuery,
    ) -> PaginatedResponse[WorkspaceCardDTO]:
        return PaginatedResponse(
            items=[],
            total=0,
            limit=query.limit,
            offset=query.offset,
            has_more=False,
            warnings=[],
        )
