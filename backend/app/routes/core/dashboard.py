"""
Dashboard API Routes

Hard rules:
- R1: Do not expose owner_user_id parameter
- R2: Cloud mode without token -> 401
- R3: Response format fully aligned with site-hub
"""

import asyncio
import logging
from typing import Optional, List
from fastapi import APIRouter, Query, Body, HTTPException, Depends, Request

from ...models.dashboard import (
    DashboardSummaryDTO,
    InboxItemDTO,
    CaseCardDTO,
    AssignmentCardDTO,
    WorkspaceCardDTO,
    DashboardQuery,
    PaginatedResponse,
    WorkspaceSetupStatus,
    SavedViewDTO,
    SavedViewCreate,
)
from ...dependencies.auth import get_current_user, AuthContext
from ...utils.scope import parse_scope, validate_scope
from ...services.dashboard_aggregator import DashboardAggregator
from ...services.saved_views_store import SavedViewsStore
from ...services.mindscape_store import MindscapeStore

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


def get_aggregator() -> DashboardAggregator:
    store = MindscapeStore()
    return DashboardAggregator(store)


def get_saved_views_store() -> SavedViewsStore:
    store = MindscapeStore()
    return SavedViewsStore(store.db_path)


# ==================== Summary ====================


@router.get("/summary", response_model=DashboardSummaryDTO)
@router.post("/summary", response_model=DashboardSummaryDTO)
async def get_dashboard_summary(
    request: Request,
    query: Optional[DashboardQuery] = Body(None),
    scope: Optional[str] = Query(None),
    view: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_current_user),
):
    """Get dashboard summary"""
    try:
        dashboard_query = query or DashboardQuery(
            scope=scope or "global",
            view=view or "my_work",
        )

        # Validate scope
        parsed_scope = parse_scope(dashboard_query.scope)
        validation = validate_scope(parsed_scope, auth)
        if not validation.is_valid:
            raise HTTPException(
                status_code=validation.error_code or 403,
                detail=validation.error_message,
            )

        aggregator = get_aggregator()
        return await aggregator.get_summary(
            auth, dashboard_query, validation.effective_scope
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get dashboard summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Inbox ====================


@router.get("/inbox", response_model=PaginatedResponse[InboxItemDTO])
@router.post("/inbox", response_model=PaginatedResponse[InboxItemDTO])
async def list_inbox_items(
    request: Request,
    query: Optional[DashboardQuery] = Body(None),
    scope: Optional[str] = Query(None),
    sort_by: str = Query("auto"),
    sort_order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_current_user),
):
    """Get inbox items"""
    try:
        dashboard_query = query or DashboardQuery(
            scope=scope or "global",
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )

        parsed_scope = parse_scope(dashboard_query.scope)
        validation = validate_scope(parsed_scope, auth)
        if not validation.is_valid:
            raise HTTPException(
                status_code=validation.error_code or 403,
                detail=validation.error_message,
            )

        aggregator = get_aggregator()
        return await aggregator.get_inbox(
            auth, dashboard_query, validation.effective_scope
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list inbox items: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Cases ====================


@router.get("/cases", response_model=PaginatedResponse[CaseCardDTO])
async def list_case_cards(
    request: Request,
    scope: Optional[str] = Query(None),
    status: Optional[List[str]] = Query(None),
    sort_by: str = Query("auto"),
    sort_order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_current_user),
):
    """Get Case card list"""
    try:
        dashboard_query = DashboardQuery(
            scope=scope or "global",
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )

        parsed_scope = parse_scope(dashboard_query.scope)
        validation = validate_scope(parsed_scope, auth)
        if not validation.is_valid:
            raise HTTPException(
                status_code=validation.error_code or 403,
                detail=validation.error_message,
            )

        aggregator = get_aggregator()
        return await aggregator.get_cases(
            auth, dashboard_query, validation.effective_scope
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Assignments ====================


@router.get("/assignments", response_model=PaginatedResponse[AssignmentCardDTO])
async def list_assignment_cards(
    request: Request,
    scope: Optional[str] = Query(None),
    view: str = Query("assigned_to_me"),
    status: Optional[List[str]] = Query(None),
    sort_by: str = Query("auto"),
    sort_order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_current_user),
):
    """Get Assignment card list"""
    try:
        dashboard_query = DashboardQuery(
            scope=scope or "global",
            view=view,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )

        parsed_scope = parse_scope(dashboard_query.scope)
        validation = validate_scope(parsed_scope, auth)
        if not validation.is_valid:
            raise HTTPException(
                status_code=validation.error_code or 403,
                detail=validation.error_message,
            )

        aggregator = get_aggregator()
        return await aggregator.get_assignments(
            auth, dashboard_query, validation.effective_scope
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list assignments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Workspaces ====================


@router.get("/workspaces", response_model=PaginatedResponse[WorkspaceCardDTO])
async def list_workspace_cards(
    request: Request,
    setup_status: Optional[WorkspaceSetupStatus] = Query(None),
    pinned_only: bool = Query(False),
    search: Optional[str] = Query(None),
    sort_by: str = Query("last_activity_at"),
    sort_order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_current_user),
):
    """Get Workspace card list"""
    try:
        dashboard_query = DashboardQuery(
            scope="global",
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )

        aggregator = get_aggregator()
        return await aggregator.get_workspaces(
            auth=auth,
            query=dashboard_query,
            search=search,
            setup_status=setup_status,
            pinned_only=pinned_only,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list workspaces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Saved Views ====================


@router.get("/saved-views", response_model=List[SavedViewDTO])
async def list_saved_views(
    request: Request,
    auth: AuthContext = Depends(get_current_user),
):
    """Get saved view list"""
    try:
        store = get_saved_views_store()
        views = await asyncio.to_thread(store.list_by_user, auth.user_id)
        return [SavedViewDTO(**v) for v in views]
    except Exception as e:
        logger.error(f"Failed to list saved views: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/saved-views", response_model=SavedViewDTO, status_code=201)
async def create_saved_view(
    request: Request,
    view_data: SavedViewCreate = Body(...),
    auth: AuthContext = Depends(get_current_user),
):
    """Create saved view"""
    try:
        store = get_saved_views_store()
        view = await asyncio.to_thread(store.create, auth.user_id, view_data.dict())
        return SavedViewDTO(**view)
    except Exception as e:
        logger.error(f"Failed to create saved view: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/saved-views/{view_id}", status_code=204)
async def delete_saved_view(
    request: Request,
    view_id: str,
    auth: AuthContext = Depends(get_current_user),
):
    """Delete saved view"""
    try:
        store = get_saved_views_store()
        deleted = await asyncio.to_thread(store.delete, view_id, auth.user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Saved view not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete saved view: {e}")
        raise HTTPException(status_code=500, detail=str(e))
