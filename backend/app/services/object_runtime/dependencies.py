"""Object runtime service helpers extracted from the route facade."""

from __future__ import annotations

import importlib
import inspect
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException, Path as PathParam, Query
from fastapi.encoders import jsonable_encoder

from backend.app.models.meeting_session import MeetingSession
from backend.app.models.object_runtime import (
    MeetingAttachmentSummary,
    ObjectAction,
    ObjectActionClosureRequest,
    ObjectActionClosureResponse,
    ObjectActionInvokeRequest,
    ObjectActionInvokeResponse,
    ObjectActionPlanRequest,
    ObjectActionPlanResponse,
    ObjectAffordanceCapability,
    ObjectCatalogEntry,
    ObjectCatalogResponse,
    ObjectGraphProjectRequest,
    ObjectGraphProjectResponse,
    ObjectGraphProjection,
    ObjectGraphProjectionCapabilities,
    ObjectGraphRelation,
    ObjectGuidanceCard,
    ObjectInstanceIndexRequest,
    ObjectInstanceIndexResponse,
    ObjectInstanceRecord,
    ObjectInstanceSyncRequest,
    ObjectInstanceSyncResponse,
    ObjectMaterializeRequest,
    ObjectMaterializeResponse,
    ObjectMaterializerCapabilities,
    ObjectMeetingAttachRequest,
    ObjectMeetingAttachResponse,
    ObjectMeetingProjectionCapabilities,
    ObjectMentionCompletionItem,
    ObjectMentionCompletionResponse,
    ObjectReadRequest,
    ObjectReadResponse,
    ObjectRef,
    ObjectRelationIndexRequest,
    ObjectRelationIndexResponse,
    ObjectRelationRecord,
    ObjectRelationSearchResponse,
    ObjectResolverCapabilities,
    ObjectRoleEntry,
    ObjectSearchResponse,
    ObjectSummary,
    ResolvedSelectionObject,
    SelectionResolveError,
    SelectionResolveRequest,
    SelectionResolveResponse,
)
from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.object_catalog_registry import ObjectCatalogRegistry
from backend.app.services.object_index_sync_service import (
    get_object_index_sync_service,
    get_object_index_sync_status,
)
from backend.app.services.object_meeting_attachment_service import (
    ObjectMeetingAttachmentService,
    ObjectMeetingContextRecord,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.object_instance_registry_store import ObjectInstanceRegistryStore
from backend.app.services.stores.object_relation_registry_store import ObjectRelationRegistryStore
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)

_workspace_store: MindscapeStore | None = None
_meeting_session_store: MeetingSessionStore | None = None
_object_meeting_attachment_service: ObjectMeetingAttachmentService | None = None
_object_instance_registry_store: ObjectInstanceRegistryStore | None = None
_object_relation_registry_store: ObjectRelationRegistryStore | None = None
_tasks_store: TasksStore | None = None

def _resolve_local_core_root() -> Path:
    return Path(__file__).resolve().parents[4]

def _get_object_catalog_registry() -> ObjectCatalogRegistry:
    return ObjectCatalogRegistry(_resolve_local_core_root())

def _get_workspace_store() -> MindscapeStore:
    global _workspace_store
    if _workspace_store is None:
        _workspace_store = MindscapeStore()
    return _workspace_store

def _get_meeting_session_store() -> MeetingSessionStore:
    global _meeting_session_store
    if _meeting_session_store is None:
        _meeting_session_store = MeetingSessionStore()
    return _meeting_session_store

def _get_object_meeting_attachment_service() -> ObjectMeetingAttachmentService:
    global _object_meeting_attachment_service
    if _object_meeting_attachment_service is None:
        _object_meeting_attachment_service = ObjectMeetingAttachmentService()
    return _object_meeting_attachment_service

def _get_object_instance_registry_store() -> ObjectInstanceRegistryStore:
    global _object_instance_registry_store
    if _object_instance_registry_store is None:
        _object_instance_registry_store = ObjectInstanceRegistryStore()
    return _object_instance_registry_store

def _get_object_relation_registry_store() -> ObjectRelationRegistryStore:
    global _object_relation_registry_store
    if _object_relation_registry_store is None:
        _object_relation_registry_store = ObjectRelationRegistryStore()
    return _object_relation_registry_store

def _get_tasks_store() -> TasksStore:
    global _tasks_store
    if _tasks_store is None:
        _tasks_store = TasksStore()
    return _tasks_store

async def _ensure_workspace_exists(workspace_id: str) -> None:
    workspace = await _get_workspace_store().get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=404, detail=f"Workspace '{workspace_id}' not found"
        )


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
