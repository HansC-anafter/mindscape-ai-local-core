"""
Workspace API routes

Main router that mounts sub-routers for different domains:
- workspace_chat: Chat and CTA handling
- workspace_timeline: Events and timeline items
- workspace_files: File upload and analysis
- workspace_tasks: Task management
- workspace_workbench: Workbench data and health checks

This file only contains workspace CRUD operations and router mounting.
All domain-specific logic is in sub-routers.

Sub-routers are loaded via pack registry.
"""

import uuid
import logging
import os
import re
import subprocess
import platform
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, HTTPException, Path as PathParam, Query, Body, File, UploadFile, Form, Depends
from pydantic import ValidationError, BaseModel, Field
from sqlalchemy.orm import Session

from ...models.workspace import (
    Workspace,
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest
)
from ...models.workspace_runtime_profile import WorkspaceRuntimeProfile
from ...services.stores.workspace_runtime_profile_store import WorkspaceRuntimeProfileStore
from ...models.runtime_environment import RuntimeEnvironment
from ...services.stores.runtime_profile_presets import (
    get_preset_templates,
    get_preset_names,
    create_security_preset,
    create_agile_preset,
    create_research_preset
)
from ...models.control_knob import ControlProfile
from ...services.stores.control_profile_store import ControlProfileStore
from ...services.knob_effect_compiler import KnobEffectCompiler
from ...services.knob_presets import PRESETS, CORE_KNOBS, SLAVE_KNOBS
from ...models.mindscape import MindEvent, EventType, EventActor, IntentTagStatus
from ...services.mindscape_store import MindscapeStore
from ...services.i18n_service import get_i18n_service
from ...services.stores.intent_tags_store import IntentTagsStore
from ...services.task_status_fix import TaskStatusFixService

# Sub-routers are loaded via pack registry
# See backend/packs/workspace-pack.yaml and backend/features/workspace/

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])

logger = logging.getLogger(__name__)

# Initialize store (singleton)
store = MindscapeStore()

# Initialize runtime profile store
def get_runtime_profile_store() -> WorkspaceRuntimeProfileStore:
    """Get runtime profile store instance"""
    return WorkspaceRuntimeProfileStore(store.db_path)

# Initialize control profile store
def get_control_profile_store() -> ControlProfileStore:
    """Get control profile store instance"""
    return ControlProfileStore(store.db_path)


# ============================================================================
# Service Imports
# ============================================================================
# Import services to keep workspace.py focused on CRUD operations
from ...services.storage_path_validator import StoragePathValidator
from ...services.storage_path_resolver import StoragePathResolver
from ...services.workspace_welcome_service import WorkspaceWelcomeService
from ...services.workspace_seed_service import WorkspaceSeedService


# ============================================================================
# Workspace Management Endpoints (CRUD)
# ============================================================================

@router.get("", response_model=List[Workspace])
async def list_workspaces(
    owner_user_id: str = Query(..., description="Owner user ID"),
    primary_project_id: Optional[str] = Query(None, description="Filter by primary project ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of workspaces"),
    include_system: bool = Query(False, description="Include system workspaces (validation, testing, etc.)"),
    group_id: Optional[str] = Query(None, description="Group ID filter (Cloud only, ignored in local-core)")
):
    """
    List workspaces for a user

    Returns list of workspaces owned by the user, optionally filtered by project.
    By default, system workspaces (is_system=true) are excluded from the list.

    Note: group_id parameter is accepted for Cloud compatibility but ignored in local-core.
    """
    try:
        workspaces = store.list_workspaces(
            owner_user_id=owner_user_id,
            primary_project_id=primary_project_id,
            limit=limit
        )
        # Filter out system workspaces unless explicitly requested
        if not include_system:
            workspaces = [ws for ws in workspaces if not getattr(ws, 'is_system', False)]
        # Note: group_id parameter is ignored in local-core (backward compatibility for Cloud)
        return workspaces
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list workspaces: {str(e)}")


@router.post("", response_model=Workspace, status_code=201)
async def create_workspace(
    request: CreateWorkspaceRequest = Body(...),
    owner_user_id: str = Query(..., description="Owner user ID")
):
    """
    Create a new workspace

    Creates a new workspace with the provided configuration.
    Includes storage path decision logic.
    """
    try:
        # Path decision logic
        # Storage path is optional during workspace creation - can be configured later in workspace settings
        # Critical: must validate path is within allowed directories after each path operation (prevent directory traversal)
        storage_base_path = None
        workspace_storage_path_str = None
        allowed_dirs = StoragePathValidator.get_allowed_directories()

        # Check if storage_base_path is specified in request
        if hasattr(request, 'storage_base_path') and request.storage_base_path:
            requested_path_str = request.storage_base_path.strip()

            # Use StoragePathValidator service for validation
            is_valid, error_message, _ = StoragePathValidator.validate_and_check_host_path(requested_path_str)
            if not is_valid:
                raise HTTPException(status_code=400, detail=error_message)

            requested_path = Path(requested_path_str).expanduser().resolve()

            if allowed_dirs:
                # When allowed directories configured, must validate
                if not StoragePathValidator.validate_path_in_allowed_directories(requested_path, allowed_dirs):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Specified path {request.storage_base_path} is not within allowed directories"
                    )
            else:
                # When no allowed directories configured, allow manual specification (but log warning)
                logger.warning(f"User manually specified path without allowed directories config: {request.storage_base_path}")

            storage_base_path = str(requested_path)

            # Generate full path: <base_path>/Mindscape/<workspace_name>/
            workspace_storage_path = Path(storage_base_path).expanduser() / "Mindscape" / request.title
            workspace_storage_path = workspace_storage_path.resolve()

            # Security check: validate final path is still within allowed directories (prevent directory traversal)
            if allowed_dirs and not StoragePathValidator.validate_path_in_allowed_directories(workspace_storage_path, allowed_dirs):
                raise HTTPException(
                    status_code=400,
                    detail=f"Generated path {workspace_storage_path} is not within allowed directories, security risk may exist"
                )

            # Create directory (if not exists)
            workspace_storage_path.mkdir(parents=True, exist_ok=True)

            # Verify directory is writable
            if not os.access(workspace_storage_path, os.W_OK):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot write to directory: {workspace_storage_path}, please check permissions"
                )

            workspace_storage_path_str = str(workspace_storage_path)
        else:
            # No storage path specified - automatically generate a default path for the workspace
            # Uses unified solution: env var > allowed directories > project data directory
            default_base = await StoragePathResolver.get_default_storage_path(store)

            if default_base:
                # Generate workspace-specific path: <base>/<workspace_title>/
                # Sanitize workspace title for use in file path
                safe_title = re.sub(r'[^\w\s-]', '', request.title).strip()
                safe_title = re.sub(r'[-\s]+', '-', safe_title)  # Replace spaces and multiple dashes with single dash
                if not safe_title:
                    safe_title = f"workspace-{uuid.uuid4().hex[:8]}"

                workspace_storage_path = Path(default_base).expanduser() / safe_title
                workspace_storage_path = workspace_storage_path.resolve()

                # Create directory (if not exists)
                try:
                    workspace_storage_path.mkdir(parents=True, exist_ok=True)

                    # Verify directory is writable
                    if not os.access(workspace_storage_path, os.W_OK):
                        logger.warning(f"Cannot write to auto-generated directory: {workspace_storage_path}, workspace will be created without storage path")
                        workspace_storage_path_str = None
                    else:
                        workspace_storage_path_str = str(workspace_storage_path)
                        logger.info(f"Auto-generated workspace storage path: {workspace_storage_path_str}")
                except Exception as e:
                    logger.warning(f"Failed to create auto-generated workspace directory {workspace_storage_path}: {e}, workspace will be created without storage path")
                    workspace_storage_path_str = None

        # Create Workspace (with storage configuration)
        # Get default_locale from request, or fallback to system settings
        if request.default_locale:
            default_locale = request.default_locale
        else:
            from ...services.system_settings_store import SystemSettingsStore
            settings_store = SystemSettingsStore(db_path=store.db_path)
            language_setting = settings_store.get_setting("default_language")
            default_locale = language_setting.value if language_setting and language_setting.value else "zh-TW"

        workspace = Workspace(
            id=str(uuid.uuid4()),
            title=request.title,
            description=request.description,
            is_system=getattr(request, 'is_system', False),
            workspace_type=request.workspace_type if hasattr(request, 'workspace_type') and request.workspace_type else None,
            owner_user_id=owner_user_id,
            primary_project_id=request.primary_project_id,
            default_playbook_id=request.default_playbook_id,
            default_locale=default_locale,
            storage_base_path=workspace_storage_path_str,
            artifacts_dir=getattr(request, 'artifacts_dir', None) or "artifacts",
            uploads_dir="uploads",
            storage_config={
                "bucket_strategy": "playbook_code",
                "naming_rule": "slug-v{version}-{timestamp}.{ext}"
            },
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        created = store.create_workspace(workspace)

        # Auto-register background routine for state sync (skip for system workspaces)
        # System workspaces are for validation/testing and should not have background routines
        if not getattr(created, 'is_system', False):
            try:
                from ...models.workspace import BackgroundRoutine
                from ...services.stores.background_routines_store import BackgroundRoutinesStore

                routines_store = BackgroundRoutinesStore(db_path=store.db_path)

                # Check if state sync routine already exists for this workspace
                existing = routines_store.get_background_routine_by_playbook(
                    workspace_id=created.id,
                    playbook_code="system_mindscape_state_sync"
                )

                if not existing:
                    # Create background routine for state sync (runs daily at 2 AM)
                    routine = BackgroundRoutine(
                        id=str(uuid.uuid4()),
                        workspace_id=created.id,
                        playbook_code="system_mindscape_state_sync",
                        schedule="0 2 * * *",  # Daily at 2 AM
                        enabled=True,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    routines_store.create_background_routine(routine)
                    logger.info(f"Auto-registered state sync background routine for workspace {created.id}")
            except Exception as e:
                logger.warning(f"Failed to register state sync background routine: {e}")
        else:
            logger.debug(f"Skipping background routine registration for system workspace {created.id}")

        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.SYSTEM,
            channel="api",
            profile_id=owner_user_id,
            project_id=request.primary_project_id,
            workspace_id=created.id,
            event_type=EventType.PROJECT_CREATED,
            payload={"workspace_id": created.id, "title": created.title},
            entity_ids=[],
            metadata={}
        )
        store.create_event(event)

        locale = created.default_locale if hasattr(created, 'default_locale') and created.default_locale else default_locale
        welcome_message, suggestions = await WorkspaceWelcomeService.generate_welcome_message(created, owner_user_id, store, locale=locale)
        if welcome_message:
            # 🆕 Get or create default thread for welcome message
            from backend.features.workspace.chat.streaming.generator import _get_or_create_default_thread
            default_thread_id = _get_or_create_default_thread(created.id, store)
            
            welcome_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.ASSISTANT,
                channel="local_workspace",
                profile_id=owner_user_id,
                project_id=request.primary_project_id,
                workspace_id=created.id,
                thread_id=default_thread_id,  # 🆕
                event_type=EventType.MESSAGE,
                payload={
                    "message": welcome_message,
                    "is_welcome": True,
                    "suggestions": suggestions
                },
                entity_ids=[],
                metadata={"is_cold_start": True}
            )
            store.create_event(welcome_event)
            
            # 🆕 Update thread statistics
            try:
                # Use COUNT query to accurately calculate message count
                message_count = store.events.count_messages_by_thread(
                    workspace_id=created.id,
                    thread_id=default_thread_id
                )
                store.conversation_threads.update_thread(
                    thread_id=default_thread_id,
                    last_message_at=datetime.utcnow(),
                    message_count=message_count
                )
            except Exception as e:
                logger.warning(f"Failed to update thread statistics for welcome message: {e}")

        return created
    except ValidationError as e:
        logger.error(f"Validation error when creating workspace: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Failed to create workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create workspace: {str(e)}")


# ============================================================================
# Workspace Launchpad API
# IMPORTANT: This route must be defined BEFORE the generic /{workspace_id} route
# to ensure FastAPI matches /launchpad correctly (more specific routes first)
# ============================================================================

@router.get("/{workspace_id}/launchpad")
async def get_workspace_launchpad(
    workspace_id: str = PathParam(..., description="Workspace ID")
):
    """
    Get workspace launchpad data

    Returns launchpad data for display:
    - brief: Workspace brief (1-2 paragraphs)
    - initial_intents: List of intent cards (3-7 items)
    - first_playbook: First playbook to run
    - tool_connections: Tool connection status
    - launch_status: Current launch status

    This endpoint is optimized for Launchpad display and returns only necessary data.
    """
    try:
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            # Return empty launchpad instead of 404 error
            # This allows the UI to show the setup state
            return {
                "brief": None,
                "initial_intents": [],
                "first_playbook": None,
                "tool_connections": [],
                "launch_status": "pending"
            }

        # Safety check: Check for execution records or event records even if no blueprint exists
        has_usage_records = False
        has_executions = False
        try:
            from ...services.stores.tasks_store import TasksStore
            tasks_store = TasksStore(store.db_path)
            executions = tasks_store.list_executions_by_workspace(workspace_id, limit=1)
            has_executions = len(executions) > 0
            if has_executions:
                logger.info(f"Workspace {workspace_id} has {len(executions)} execution(s)")
        except Exception as e:
            logger.warning(f"Failed to check executions for workspace {workspace_id}: {e}")

        # Check for event records (conversations, messages, etc.)
        try:
            events = store.get_events_by_workspace(workspace_id, limit=1)
            has_usage_records = len(events) > 0
            if has_usage_records:
                logger.info(f"Workspace {workspace_id} has {len(events)} event(s)")
        except Exception as e:
            logger.warning(f"Failed to check events for workspace {workspace_id}: {e}")

        # Auto-update status if workspace has execution/event records but status is pending
        current_status = workspace.launch_status.value if workspace.launch_status else "pending"
        if current_status == "pending":
            if has_executions:
                # Has execution records -> active
                try:
                    from ...models.workspace import LaunchStatus
                    workspace.launch_status = LaunchStatus.ACTIVE
                    store.update_workspace(workspace)
                    logger.info(f"Auto-updated workspace {workspace_id} status from pending to active (has executions)")
                    current_status = "active"
                except Exception as e:
                    logger.warning(f"Failed to auto-update workspace status to active: {e}")
            elif has_usage_records:
                # Has event records -> ready
                try:
                    from ...models.workspace import LaunchStatus
                    workspace.launch_status = LaunchStatus.READY
                    store.update_workspace(workspace)
                    logger.info(f"Auto-updated workspace {workspace_id} status from pending to ready (has usage records)")
                    current_status = "ready"
                except Exception as e:
                    logger.warning(f"Failed to auto-update workspace status to ready: {e}")

        blueprint = workspace.workspace_blueprint
        if not blueprint:
            # Return empty launchpad if no blueprint
            return {
                "brief": None,
                "initial_intents": [],
                "first_playbook": None,
                "tool_connections": [],
                "launch_status": current_status
            }

        # Check blueprint content
        has_blueprint_content = (
            (blueprint.brief and blueprint.brief.strip()) or
            (blueprint.initial_intents and len(blueprint.initial_intents) > 0) or
            (blueprint.tool_connections and len(blueprint.tool_connections) > 0)
        )

        # Auto-update status to ready if workspace has blueprint content but status is pending
        if current_status == "pending" and has_blueprint_content:
            try:
                from ...models.workspace import LaunchStatus
                workspace.launch_status = LaunchStatus.READY
                store.update_workspace(workspace)
                logger.info(f"Auto-updated workspace {workspace_id} status from pending to ready (has blueprint content)")
                current_status = "ready"
            except Exception as e:
                logger.warning(f"Failed to auto-update workspace status to ready: {e}")

        return {
            "brief": blueprint.brief,
            "initial_intents": blueprint.initial_intents or [],
            "first_playbook": blueprint.first_playbook,
            "tool_connections": [
                {
                    "tool_type": conn.tool_type,
                    "danger_level": conn.danger_level,
                    "default_readonly": conn.default_readonly,
                    "allowed_roles": conn.allowed_roles
                }
                for conn in (blueprint.tool_connections or [])
            ],
            "launch_status": current_status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workspace launchpad: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get launchpad: {str(e)}")


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str = PathParam(..., description="Workspace ID")
):
    """
    Get workspace by ID

    Returns workspace details including configuration, metadata, and associated intent.
    Includes workspace_blueprint for Launchpad display.
    """
    import asyncio
    import time
    request_id = f"req-{int(time.time() * 1000)}-{id(asyncio.current_task())}"
    logger.info(f"[{request_id}] GET /workspaces/{workspace_id} - Request started")

    try:
        logger.info(f"[{request_id}] Getting workspace from store...")
        workspace = store.get_workspace(workspace_id)
        logger.info(f"[{request_id}] Workspace retrieved: {workspace.id if workspace else 'None'}")

        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        associated_intent = None
        if workspace.primary_project_id:
            try:
                from ...services.stores.intents_store import IntentsStore
                intents_store = IntentsStore(store.db_path)
                intent = intents_store.get_intent(workspace.primary_project_id)
                if intent:
                    associated_intent = {
                        "id": intent.id,
                        "title": intent.title,
                        "tags": intent.tags,
                        "status": intent.status.value,
                        "priority": intent.priority.value
                    }
            except Exception as e:
                logger.warning(f"Failed to fetch associated intent: {e}")

        workspace_dict = workspace.dict()
        if associated_intent:
            workspace_dict["associated_intent"] = associated_intent

        logger.info(f"[{request_id}] Returning workspace data")
        return workspace_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Error getting workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get workspace: {str(e)}")


@router.put("/{workspace_id}", response_model=Workspace)
async def update_workspace(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: UpdateWorkspaceRequest = Body(...)
):
    """
    Update an existing workspace

    Updates workspace fields. Only provided fields will be updated.
    """
    try:
        logger.info(f"Updating workspace {workspace_id} with request: {request.dict(exclude_unset=True)}")
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Path change risk handling: check if storage_base_path or artifacts_dir changed
        old_storage_base_path = workspace.storage_base_path
        old_artifacts_dir = workspace.artifacts_dir
        storage_path_changed = False

        if request.title is not None:
            workspace.title = request.title
        if request.description is not None:
            workspace.description = request.description
        if request.workspace_type is not None:
            workspace.workspace_type = request.workspace_type
        if request.primary_project_id is not None:
            workspace.primary_project_id = request.primary_project_id
        if request.default_playbook_id is not None:
            workspace.default_playbook_id = request.default_playbook_id
        if request.default_locale is not None:
            workspace.default_locale = request.default_locale
        request_dict = request.dict(exclude_unset=False)
        if 'mode' in request_dict:
            workspace.mode = request.mode
        if hasattr(request, 'playbook_storage_config') and request.playbook_storage_config is not None:
            workspace.playbook_storage_config = request.playbook_storage_config

        # Handle storage path update (if these fields exist in request)
        if hasattr(request, 'storage_base_path') and request.storage_base_path is not None:
            if request.storage_base_path != old_storage_base_path:
                storage_path_changed = True
                # Validate new path using StoragePathValidator service
                is_valid, error_message, _ = StoragePathValidator.validate_and_check_host_path(request.storage_base_path)
                if not is_valid:
                    raise HTTPException(status_code=400, detail=error_message)

                new_path = Path(request.storage_base_path).expanduser().resolve()

                if not new_path.exists():
                    try:
                        new_path.mkdir(parents=True, exist_ok=True)
                        logger.info(f"Created storage directory: {new_path}")
                        # Verify directory was actually created
                        if not new_path.exists():
                            logger.warning(f"Directory creation reported success but path does not exist: {new_path}")
                            raise HTTPException(
                                status_code=400,
                                detail=f"Failed to create storage path {new_path}. Directory may not be accessible from container."
                            )
                    except PermissionError as e:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Permission denied when creating storage path {new_path}: {str(e)}. Please check Docker Desktop file sharing settings."
                        )
                    except Exception as e:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Failed to create storage path {new_path}: {str(e)}"
                        )
                if not os.access(new_path, os.W_OK):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Storage path is not writable: {new_path}. Please check directory permissions and Docker Desktop file sharing settings."
                    )
                # Validate path is within allowed directories
                allowed_dirs = StoragePathValidator.get_allowed_directories()
                if allowed_dirs and not StoragePathValidator.validate_path_in_allowed_directories(new_path, allowed_dirs):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Storage path {new_path} is not within allowed directories. This may indicate a security issue."
                    )
                workspace.storage_base_path = request.storage_base_path
                logger.warning(
                    f"Workspace {workspace_id} storage_base_path changed from {old_storage_base_path} to {request.storage_base_path}. "
                    "Existing artifacts may not be automatically found. Consider migrating artifacts manually."
                )

        if hasattr(request, 'artifacts_dir') and request.artifacts_dir is not None:
            if request.artifacts_dir != old_artifacts_dir:
                storage_path_changed = True
                workspace.artifacts_dir = request.artifacts_dir
                logger.warning(
                    f"Workspace {workspace_id} artifacts_dir changed from {old_artifacts_dir} to {request.artifacts_dir}. "
                    "Existing artifacts may not be automatically found. Consider migrating artifacts manually."
                )

        # Handle playbook_storage_config update
        if hasattr(request, 'playbook_storage_config') and request.playbook_storage_config is not None:
            # Validate playbook storage config paths
            for playbook_code, config in request.playbook_storage_config.items():
                if not isinstance(config, dict):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid playbook_storage_config for {playbook_code}: must be a dict"
                    )
                base_path = config.get('base_path')
                if base_path:
                    # Validate path using StoragePathValidator service
                    is_valid, error_message, _ = StoragePathValidator.validate_and_check_host_path(base_path)
                    if not is_valid:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Playbook storage path {base_path} for {playbook_code}: {error_message}"
                        )

                    new_path = Path(base_path).expanduser().resolve()

                    if not new_path.exists():
                        try:
                            new_path.mkdir(parents=True, exist_ok=True)
                            logger.info(f"Created playbook storage directory: {new_path}")
                        except Exception as e:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Failed to create playbook storage path {new_path} for {playbook_code}: {str(e)}"
                            )
                    if not os.access(new_path, os.W_OK):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Playbook storage path is not writable: {new_path} for {playbook_code}. Please check directory permissions."
                        )
                    # Validate path is within allowed directories
                    allowed_dirs = StoragePathValidator.get_allowed_directories()
                    if allowed_dirs and not StoragePathValidator.validate_path_in_allowed_directories(new_path, allowed_dirs):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Playbook storage path {new_path} for {playbook_code} is not within allowed directories. This may indicate a security issue."
                        )
            workspace.playbook_storage_config = request.playbook_storage_config
            logger.info(f"Updated playbook_storage_config for workspace {workspace_id}")

        # Handle execution mode settings
        if hasattr(request, 'execution_mode') and request.execution_mode is not None:
            workspace.execution_mode = request.execution_mode
            logger.info(f"Updated execution_mode for workspace {workspace_id}: {request.execution_mode}")
        if hasattr(request, 'expected_artifacts') and request.expected_artifacts is not None:
            workspace.expected_artifacts = request.expected_artifacts
            logger.info(f"Updated expected_artifacts for workspace {workspace_id}: {request.expected_artifacts}")
        if hasattr(request, 'execution_priority') and request.execution_priority is not None:
            workspace.execution_priority = request.execution_priority
            logger.info(f"Updated execution_priority for workspace {workspace_id}: {request.execution_priority}")
        if hasattr(request, 'capability_profile') and request.capability_profile is not None:
            workspace.capability_profile = request.capability_profile
            logger.info(f"Updated capability_profile for workspace {workspace_id}: {request.capability_profile}")

        # If path changed, record warning to event system
        if storage_path_changed:
            warning_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.SYSTEM,
                channel="api",
                profile_id=workspace.owner_user_id,
                project_id=workspace.primary_project_id,
                workspace_id=workspace_id,
                event_type=EventType.PROJECT_UPDATED,
                payload={
                    "workspace_id": workspace_id,
                    "warning": "storage_path_changed",
                    "message": "Workspace storage path has been changed. Existing artifacts may not be automatically found. Consider migrating artifacts manually.",
                    "old_storage_base_path": old_storage_base_path,
                    "new_storage_base_path": workspace.storage_base_path,
                    "old_artifacts_dir": old_artifacts_dir,
                    "new_artifacts_dir": workspace.artifacts_dir
                },
                entity_ids=[workspace_id],
                metadata={"is_storage_path_change": True}
            )
            store.create_event(warning_event)

        updated = store.update_workspace(workspace)
        logger.info(f"Workspace {workspace_id} updated successfully. Storage path: {updated.storage_base_path}, Artifacts dir: {updated.artifacts_dir}")

        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.SYSTEM,
            channel="api",
            profile_id=workspace.owner_user_id,
            project_id=workspace.primary_project_id,
            workspace_id=workspace_id,
            event_type=EventType.PROJECT_UPDATED,
            payload={"workspace_id": workspace_id, "updated_fields": request.dict(exclude_unset=True)},
            entity_ids=[],
            metadata={}
        )
        store.create_event(event)

        return updated
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update workspace: {str(e)}")


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str = PathParam(..., description="Workspace ID")
):
    """
    Delete a workspace

    Permanently deletes the workspace and all associated data.
    """
    try:
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        store.delete_workspace(workspace_id)
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete workspace: {str(e)}")


@router.patch("/{workspace_id}/playbook-auto-exec-config", response_model=Workspace)
async def update_playbook_auto_exec_config(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = Body(..., description="Playbook code"),
    confidence_threshold: Optional[float] = Body(None, description="Confidence threshold (0.0-1.0)"),
    auto_execute: Optional[bool] = Body(None, description="Enable auto-execute")
):
    """
    Update playbook auto-execution configuration

    Sets the confidence threshold and auto-execute flag for a specific playbook in this workspace.
    """
    try:
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Initialize config if not exists
        if workspace.playbook_auto_execution_config is None:
            workspace.playbook_auto_execution_config = {}

        # Update or create playbook config
        if playbook_code not in workspace.playbook_auto_execution_config:
            workspace.playbook_auto_execution_config[playbook_code] = {}

        if confidence_threshold is not None:
            workspace.playbook_auto_execution_config[playbook_code]['confidence_threshold'] = confidence_threshold
        if auto_execute is not None:
            workspace.playbook_auto_execution_config[playbook_code]['auto_execute'] = auto_execute

        updated = store.update_workspace(workspace)
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update playbook auto-exec config: {str(e)}")


@router.post("/{workspace_id}/open-folder")
async def open_folder(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    path: str = Body(..., description="Path to open")
):
    """
    Open folder in system file manager

    Opens the specified path in the system's default file manager.
    Supports macOS, Windows, and Linux.
    """
    try:
        # Verify workspace exists
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Validate path exists
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")

        # Open folder based on platform
        system = platform.system()
        try:
            if system == "Darwin":  # macOS
                subprocess.run(["open", str(path_obj)], check=True)
            elif system == "Windows":
                subprocess.run(["explorer", str(path_obj)], check=True)
            else:  # Linux and others
                subprocess.run(["xdg-open", str(path_obj)], check=True)

            return {"success": True, "message": f"Opened folder: {path}"}
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to open folder: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to open folder. Please open manually: {path}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error opening folder: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {str(e)}")


@router.get("/{workspace_id}/intent-tags/candidates")
async def get_candidate_intent_tags(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    message_id: Optional[str] = Query(None, description="Filter by message ID"),
    limit: int = Query(10, description="Maximum number of tags to return")
):
    """
    Get candidate intent tags for a workspace

    Returns list of candidate (not yet confirmed) intent tags, typically shown after user input
    to suggest possible directions the AI sees.
    """
    try:
        intent_tags_store = IntentTagsStore(db_path=store.db_path)

        # Get candidate intent tags for this workspace
        candidate_tags = intent_tags_store.list_intent_tags(
            workspace_id=workspace_id,
            status=IntentTagStatus.CANDIDATE,
            limit=limit
        )

        # Filter by message_id if provided
        if message_id:
            candidate_tags = [tag for tag in candidate_tags if tag.message_id == message_id]

        # Convert to dict for JSON response
        tags_dict = []
        for tag in candidate_tags:
            tag_dict = {
                "id": tag.id,
                "title": tag.label,  # IntentTag uses 'label' field
                "description": tag.metadata.get("description") if tag.metadata else None,
                "confidence": tag.confidence,
                "source": tag.source.value,
                "status": tag.status.value,
                "message_id": tag.message_id,
                "created_at": tag.created_at.isoformat() if tag.created_at else None
            }
            tags_dict.append(tag_dict)

        return {"intent_tags": tags_dict, "count": len(tags_dict)}

    except Exception as e:
        logger.error(f"Failed to get candidate intent tags: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/intent-tags/{intent_tag_id}/confirm")
async def confirm_intent_tag(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    intent_tag_id: str = PathParam(..., description="Intent Tag ID")
):
    """
    Confirm an intent tag (candidate -> confirmed)

    This action marks a candidate intent as confirmed by the user and writes it to long-term memory (IntentCard).
    Only confirmed intents are written to long-term memory.
    """
    try:
        intent_tags_store = IntentTagsStore(db_path=store.db_path)

        # Get the intent tag to verify it belongs to this workspace
        intent_tag = intent_tags_store.get_intent_tag(intent_tag_id)
        if not intent_tag:
            raise HTTPException(status_code=404, detail="Intent tag not found")

        if intent_tag.workspace_id != workspace_id:
            raise HTTPException(status_code=403, detail="Intent tag belongs to different workspace")

        # Confirm the intent
        success = intent_tags_store.confirm_intent(intent_tag_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to confirm intent tag")

        # Write confirmed intent to long-term memory (IntentCard)
        try:
            from ...models.mindscape import IntentCard, IntentStatus, PriorityLevel
            from datetime import datetime
            import uuid

            # Get workspace to find profile_id
            workspace_obj = store.get_workspace(workspace_id)
            if not workspace_obj:
                logger.warning(f"Workspace {workspace_id} not found, skipping IntentCard creation")
            else:
                profile_id = workspace_obj.owner_user_id

                # Check if IntentCard with same title already exists
                existing_intents = store.list_intents(
                    profile_id=profile_id,
                    status=None,
                    priority=None
                )
                intent_exists = any(
                    intent.title == intent_tag.label or
                    intent_tag.label in intent.title
                    for intent in existing_intents
                )

                if not intent_exists:
                    # Create IntentCard from confirmed IntentTag
                    new_intent = IntentCard(
                        id=str(uuid.uuid4()),
                        profile_id=profile_id,
                        title=intent_tag.label,
                        description=intent_tag.metadata.get("description", "") if intent_tag.metadata else "",
                        status=IntentStatus.ACTIVE,
                        priority=PriorityLevel.MEDIUM,
                        tags=[],
                        category="confirmed_intent_tag",
                        progress_percentage=0.0,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        started_at=None,
                        completed_at=None,
                        due_date=None,
                        parent_intent_id=None,
                        child_intent_ids=[],
                        metadata={
                            "source": "confirmed_intent_tag",
                            "workspace_id": workspace_id,
                            "intent_tag_id": intent_tag_id,
                            "message_id": intent_tag.message_id,
                            "confidence": intent_tag.confidence
                        }
                    )
                    store.create_intent(new_intent)
                    logger.info(f"Created IntentCard {new_intent.id} from confirmed IntentTag {intent_tag_id}")
                else:
                    logger.info(f"IntentCard with title '{intent_tag.label}' already exists, skipping creation")

        except Exception as e:
            logger.error(f"Failed to create IntentCard from confirmed IntentTag: {e}", exc_info=True)
            # Don't fail the confirmation if IntentCard creation fails

        return {"success": True, "intent_tag_id": intent_tag_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to confirm intent tag: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{workspace_id}/intent-tags/{intent_tag_id}/label")
async def update_intent_tag_label(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    intent_tag_id: str = PathParam(..., description="Intent Tag ID"),
    request: dict = Body(..., description="Request body with 'label' field")
):
    """
    Update intent tag label

    Allows users to edit the label of an intent tag.
    """
    try:
        intent_tags_store = IntentTagsStore(db_path=store.db_path)

        # Get the intent tag to verify it belongs to this workspace
        intent_tag = intent_tags_store.get_intent_tag(intent_tag_id)
        if not intent_tag:
            raise HTTPException(status_code=404, detail="Intent tag not found")

        if intent_tag.workspace_id != workspace_id:
            raise HTTPException(status_code=403, detail="Intent tag belongs to different workspace")

        # Get label from request body
        label = request.get("label")
        if not label or not isinstance(label, str) or not label.strip():
            raise HTTPException(status_code=400, detail="Label is required and must be a non-empty string")

        # Update the label
        success = intent_tags_store.update_intent_tag_label(intent_tag_id, label.strip())
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update intent tag label")

        return {"success": True, "intent_tag_id": intent_tag_id, "label": label}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update intent tag label: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Tasks, Workbench, and Health Endpoints
# ============================================================================

@router.get("/{workspace_id}/tasks")
async def get_workspace_tasks(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of tasks"),
    include_completed: bool = Query(False, description="Include completed tasks")
):
    """Get tasks for a workspace"""
    try:
        from ...services.stores.tasks_store import TasksStore
        tasks_store = TasksStore(db_path=store.db_path)

        if include_completed:
            all_tasks = tasks_store.list_tasks_by_workspace(workspace_id, limit=limit)
        else:
            pending = tasks_store.list_pending_tasks(workspace_id)
            running = tasks_store.list_running_tasks(workspace_id)
            all_tasks = (pending + running)[:limit]

        return {
            "tasks": [task.dict() for task in all_tasks]
        }
    except Exception as e:
        logger.error(f"Failed to get workspace tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/ai-team-members")
async def get_ai_team_members(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_codes: Optional[str] = Query(None, description="Comma-separated list of playbook codes")
):
    """Get AI team members for given playbook codes"""
    try:
        from ...services.ai_team_service import get_member_info

        playbook_codes_list = []
        if playbook_codes:
            playbook_codes_list = [code.strip() for code in playbook_codes.split(',') if code.strip()]

        members = []
        for playbook_code in playbook_codes_list:
            member_info = get_member_info(playbook_code)
            if member_info and member_info.get("visible", True):
                members.append(member_info)

        # Sort by order
        members.sort(key=lambda m: m.get("order", 999))

        return {
            "members": members,
            "count": len(members)
        }
    except Exception as e:
        logger.error(f"Failed to get AI team members: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class RejectTaskRequest(BaseModel):
    """Request model for rejecting a task"""
    reason_code: Optional[str] = Field(None, description="Rejection reason code")
    comment: Optional[str] = Field(None, description="Optional comment explaining rejection")


@router.post("/{workspace_id}/tasks/{task_id}/reject")
async def reject_task(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    task_id: str = PathParam(..., description="Task ID"),
    request: RejectTaskRequest = Body(...)
):
    """Reject a task"""
    try:
        from ...services.stores.tasks_store import TasksStore
        from ...services.stores.task_feedback_store import TaskFeedbackStore
        from ...models.workspace import TaskFeedback, TaskFeedbackAction, TaskFeedbackReasonCode

        tasks_store = TasksStore(db_path=store.db_path)
        feedback_store = TaskFeedbackStore(db_path=store.db_path)

        task = tasks_store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.workspace_id != workspace_id:
            raise HTTPException(status_code=403, detail="Task does not belong to this workspace")

        reason_code_enum = None
        if request.reason_code:
            try:
                reason_code_enum = TaskFeedbackReasonCode(request.reason_code)
            except ValueError:
                logger.warning(f"Invalid reason_code: {request.reason_code}")

        feedback = TaskFeedback(
            id=str(uuid.uuid4()),
            task_id=task_id,
            workspace_id=workspace_id,
            user_id="default-user",
            action=TaskFeedbackAction.REJECT,
            reason_code=reason_code_enum,
            comment=request.comment
        )

        feedback_store.create_feedback(feedback)

        return {
            "success": True,
            "message": "Task rejected successfully",
            "feedback_id": feedback.id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/workbench")
async def get_workspace_workbench(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    profile_id: str = Query("default-user", description="Profile ID")
):
    """Get workbench data for a workspace"""
    try:
        from ...services.workbench_service import WorkbenchService
        workbench_service = WorkbenchService(store=store)
        data = await workbench_service.get_workbench_data(workspace_id, profile_id)
        return data
    except Exception as e:
        logger.error(f"Failed to get workbench data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/workbench/context-token-count")
async def get_workspace_context_token_count(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    profile_id: str = Query("default-user", description="Profile ID")
):
    """Get context token count for workspace workbench"""
    try:
        from ...services.conversation.context_builder import ContextBuilder
        from ...services.conversation.model_context_presets import get_context_preset

        store = MindscapeStore()
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Get model name from system settings - must be configured by user
        from backend.app.services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore()
        chat_setting = settings_store.get_setting("chat_model")

        if not chat_setting or not chat_setting.value:
            raise ValueError(
                "LLM model not configured. Please select a model in the system settings panel."
            )

        model_name = str(chat_setting.value)
        if not model_name or model_name.strip() == "":
            raise ValueError(
                "LLM model is empty. Please select a valid model in the system settings panel."
            )

        context_builder = ContextBuilder(
            store=store,
            model_name=model_name
        )

        enhanced_prompt = await context_builder.build_qa_context(
            workspace_id=workspace_id,
            message="",
            profile_id=profile_id,
            workspace=workspace
        )
        token_count = context_builder.estimate_token_count(enhanced_prompt, model_name) or 0

        return {
            "workspace_id": workspace_id,
            "token_count": token_count,
            "model_name": model_name
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get context token count: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/health")
async def get_workspace_health(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    profile_id: str = Query("default-user", description="Profile ID")
):
    """Get health status for a workspace"""
    try:
        from ...services.system_health_checker import SystemHealthChecker
        health_checker = SystemHealthChecker()
        health = await health_checker.check_workspace_health(profile_id, workspace_id)
        return health
    except Exception as e:
        logger.error(f"Failed to get workspace health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/fix-task-status")
async def fix_task_status(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    create_timeline_items: bool = Query(True, description="Create timeline items for fixed tasks"),
    limit: Optional[int] = Query(None, description="Maximum number of tasks to fix")
):
    """
    Fix tasks with inconsistent status

    Finds and fixes tasks where:
    - task.status = "running"
    - execution_context.status = "completed" or "failed"

    This happens when PlaybookRunExecutor didn't properly update task status.
    """
    try:
        fix_service = TaskStatusFixService()
        result = fix_service.fix_all_inconsistent_tasks(
            workspace_id=workspace_id,
            create_timeline_items=create_timeline_items,
            limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Failed to fix task status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# File Upload and Analysis Endpoints
# ============================================================================

@router.post("/{workspace_id}/files/upload")
async def upload_file(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    file: UploadFile = File(...),
    file_name: Optional[str] = Form(None),
    file_type: Optional[str] = Form(None),
    file_size: Optional[int] = Form(None)
):
    """
    Upload file to workspace

    Supports multipart/form-data:
    - file: File to upload
    - file_name: File name (optional, defaults to uploaded file name)
    - file_type: File MIME type (optional)
    - file_size: File size in bytes (optional)
    """
    try:
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        import base64
        from ...services.file_analysis_service import FileAnalysisService
        from ...services.stores.timeline_items_store import TimelineItemsStore
        from ...services.stores.tasks_store import TasksStore

        timeline_items_store = TimelineItemsStore(db_path=store.db_path)
        tasks_store = TasksStore(db_path=store.db_path)
        file_service = FileAnalysisService(store, timeline_items_store, tasks_store)

        # Read file content
        file_content = await file.read()

        # Convert to base64 data URL
        file_base64 = base64.b64encode(file_content).decode('utf-8')
        file_data_url = f"data:{file.content_type or 'application/octet-stream'};base64,{file_base64}"

        # Use provided file_name or fallback to uploaded file name
        actual_file_name = file_name or file.filename or "uploaded_file"
        actual_file_type = file_type or file.content_type
        actual_file_size = file_size or len(file_content)

        result = await file_service.upload_file(
            workspace_id=workspace_id,
            file_data=file_data_url,
            file_name=actual_file_name,
            file_type=actual_file_type,
            file_size=actual_file_size
        )

        return {
            "file_id": result["file_id"],
            "file_path": result["file_path"],
            "file_name": result["file_name"],
            "file_type": result.get("file_type"),
            "file_size": result.get("file_size")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Workspace Seed API (MFR - Minimum File Reference)
# ============================================================================

@router.post("/{workspace_id}/seed")
async def process_workspace_seed(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    seed_type: str = Body(..., description="Seed type: 'text' | 'file' | 'urls'"),
    payload: Any = Body(..., description="Seed payload (text string, file data, or list of {url, note} dicts)"),
    locale: str = Body("zh-TW", description="Locale for LLM generation")
):
    """
    Process workspace seed and generate blueprint digest (MFR)

    This endpoint processes a seed input (text/file/urls) and generates a workspace blueprint
    without requiring full knowledge base import or embedding.

    Args:
        workspace_id: Workspace ID
        seed_type: Seed type ("text" | "file" | "urls")
        payload: Seed payload:
            - For "text": string
            - For "file": file data (base64 or file path)
            - For "urls": list of {"url": str, "note": str} dicts
        locale: Locale for LLM generation (default: "zh-TW")

    Returns:
        {
            "brief": str,
            "facts": List[str],
            "unknowns": List[str],
            "next_actions": List[str],
            "intents": List[Dict],
            "starter_kit_type": str,
            "first_playbook": str
        }
    """
    try:
        # Validate workspace exists
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        # Validate seed_type
        if seed_type not in ["text", "file", "urls"]:
            raise HTTPException(status_code=400, detail=f"Invalid seed_type: {seed_type}. Must be 'text', 'file', or 'urls'")

        # Process seed
        seed_service = WorkspaceSeedService(store)
        digest = await seed_service.process_seed(
            workspace_id=workspace_id,
            seed_type=seed_type,
            payload=payload,
            locale=locale
        )

        return digest

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process workspace seed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process seed: {str(e)}")


@router.post("/{workspace_id}/files/analyze")
async def analyze_file(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: dict = Body(...)
):
    """
    Analyze uploaded file

    Request body:
    - file_id: File ID from upload (preferred)
    - file_data: Base64 encoded file data (fallback)
    - file_name: File name
    - file_type: File MIME type (optional)
    - file_size: File size in bytes (optional)
    - file_path: File path on server (optional)
    """
    try:
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        from ...services.file_analysis_service import FileAnalysisService
        from ...services.stores.timeline_items_store import TimelineItemsStore
        from ...services.stores.tasks_store import TasksStore

        timeline_items_store = TimelineItemsStore(db_path=store.db_path)
        tasks_store = TasksStore(db_path=store.db_path)
        file_service = FileAnalysisService(store, timeline_items_store, tasks_store)

        file_id = request.get("file_id")
        file_data = request.get("file_data")
        file_name = request.get("file_name")
        file_type = request.get("file_type")
        file_size = request.get("file_size")
        file_path = request.get("file_path")

        if not file_id and not file_data:
            raise HTTPException(status_code=400, detail="Either file_id or file_data is required")
        if not file_name:
            raise HTTPException(status_code=400, detail="file_name is required")

        profile_id = workspace.owner_user_id
        result = await file_service.analyze_file(
            workspace_id=workspace_id,
            profile_id=profile_id,
            file_id=file_id,
            file_data=file_data,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path
        )

        return {
            "file_id": result.get("file_id"),
            "file_path": result.get("file_path"),
            "event_id": result.get("event_id"),
            "saved_file_path": result.get("file_path"),
            "collaboration_results": result.get("collaboration_results", {})
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to analyze file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Runtime Profile Endpoints
# ============================================================================

@router.get(
    "/{workspace_id}/runtime-profile",
    response_model=WorkspaceRuntimeProfile,
    summary="Get workspace runtime profile",
    description="""
    Get the runtime profile configuration for a workspace.

    The runtime profile defines execution contracts, interaction budgets, output contracts,
    confirmation policies, and tool policies for the workspace.

    **Returns:**
    - If a profile exists: Returns the configured runtime profile
    - If no profile exists: Returns a default profile with standard settings

    **Example Response:**
    ```json
    {
        "default_mode": "execution",
        "interaction_budget": {
            "max_questions_per_turn": 0,
            "assume_defaults": true
        },
        "output_contract": {
            "coding_style": "patch_first",
            "minimize_explanation": true
        },
        "confirmation_policy": {
            "auto_read": true,
            "confirm_external_write": true
        },
        "tool_policy": {
            "allowlist": ["code_editor", "file_manager"]
        }
    }
    ```
    """,
    tags=["runtime-profile"],
    responses={
        200: {
            "description": "Runtime profile retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "default_mode": "execution",
                        "interaction_budget": {
                            "max_questions_per_turn": 0,
                            "assume_defaults": True
                        }
                    }
                }
            }
        },
        404: {"description": "Workspace not found"},
        500: {"description": "Internal server error"}
    }
)
async def get_runtime_profile(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123")
):
    """
    Get workspace runtime profile

    Returns the runtime profile configuration for the workspace.
    If no profile exists, returns a default profile.
    """
    try:
        profile_store = get_runtime_profile_store()
        profile = profile_store.get_runtime_profile(workspace_id)

        if not profile:
            # Return default profile if not found
            profile = profile_store.create_default_profile(workspace_id)

        return profile
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get runtime profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get runtime profile: {str(e)}")


@router.put(
    "/{workspace_id}/runtime-profile",
    response_model=WorkspaceRuntimeProfile,
    summary="Update workspace runtime profile",
    description="""
    Update or create the runtime profile configuration for a workspace.

    **Request Body:**
    The request body should contain a complete `WorkspaceRuntimeProfile` object with all desired settings.

    **Best Practices:**
    1. Use preset templates for common configurations (see `/runtime-profile/presets`)
    2. Start with minimal changes and iterate
    3. Test configuration in a development workspace first
    4. Document changes using `updated_reason` parameter

    **Example Request (Cursor-style configuration):**
    ```json
    {
        "default_mode": "execution",
        "interaction_budget": {
            "max_questions_per_turn": 0,
            "assume_defaults": true,
            "require_assumptions_list": true
        },
        "output_contract": {
            "coding_style": "patch_first",
            "minimize_explanation": true,
            "show_rationale_level": "brief"
        },
        "confirmation_policy": {
            "auto_read": true,
            "confirm_external_write": true,
            "confirmation_format": "list_changes"
        },
        "tool_policy": {
            "allowlist": ["code_editor", "file_manager"]
        }
    }
    ```

    **Note:** Partial updates are not supported. You must provide the complete profile configuration.
    """,
    tags=["runtime-profile"],
    responses={
        200: {
            "description": "Runtime profile updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "default_mode": "execution",
                        "interaction_budget": {
                            "max_questions_per_turn": 0,
                            "assume_defaults": True
                        }
                    }
                }
            }
        },
        404: {"description": "Workspace not found"},
        400: {"description": "Invalid profile configuration"},
        500: {"description": "Internal server error"}
    }
)
async def update_runtime_profile(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123"),
    profile: WorkspaceRuntimeProfile = Body(..., description="Runtime profile configuration"),
    updated_by: Optional[str] = Query(None, description="User ID who updated this profile", example="user_456"),
    updated_reason: Optional[str] = Query(None, description="Reason for update", example="Enable Cursor-style execution")
):
    """
    Update workspace runtime profile

    Updates or creates the runtime profile configuration for the workspace.
    """
    try:
        # Verify workspace exists
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        profile_store = get_runtime_profile_store()
        updated_profile = profile_store.save_runtime_profile(
            workspace_id=workspace_id,
            profile=profile,
            updated_by=updated_by,
            updated_reason=updated_reason
        )

        return updated_profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update runtime profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update runtime profile: {str(e)}")


@router.delete(
    "/{workspace_id}/runtime-profile",
    status_code=204,
    summary="Delete workspace runtime profile",
    description="""
    Delete the runtime profile configuration for a workspace.

    **Warning:** This will remove all custom runtime profile settings.
    The workspace will revert to default behavior after deletion.

    **Note:** This operation cannot be undone. Consider backing up the profile
    configuration before deletion if you may need to restore it later.
    """,
    tags=["runtime-profile"],
    responses={
        204: {"description": "Runtime profile deleted successfully"},
        404: {"description": "Runtime profile not found"},
        500: {"description": "Internal server error"}
    }
)
async def delete_runtime_profile(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123")
):
    """
    Delete workspace runtime profile

    Removes the runtime profile configuration for the workspace.
    """
    try:
        profile_store = get_runtime_profile_store()
        deleted = profile_store.delete_runtime_profile(workspace_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Runtime profile not found")

        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete runtime profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete runtime profile: {str(e)}")


@router.get(
    "/runtime-profile/presets",
    summary="Get runtime profile preset templates",
    description="""
    Get available runtime profile preset templates.

    Preset templates provide pre-configured runtime profiles for common use cases:

    - **security**: Strict confirmation policies, complete quality gates, conservative tool policies
    - **agile**: Minimal confirmation, fast execution, relaxed tool policies
    - **research**: Detailed output, citation requirements, complete decision logs

    **Usage:**
    1. Get available presets using this endpoint
    2. Apply a preset using `POST /{workspace_id}/runtime-profile/apply-preset`
    3. Optionally customize the applied preset using `PUT /{workspace_id}/runtime-profile`
    """,
    tags=["runtime-profile"],
    responses={
        200: {
            "description": "List of available preset templates",
            "content": {
                "application/json": {
                    "example": {
                        "presets": [
                            {
                                "name": "security",
                                "label": "安全模板",
                                "description": "嚴格確認政策、完整品質關卡、保守工具政策",
                                "icon": "🛡️"
                            },
                            {
                                "name": "agile",
                                "label": "敏捷模板",
                                "description": "最小確認、快速執行、寬鬆工具政策",
                                "icon": "⚡"
                            }
                        ]
                    }
                }
            }
        }
    }
)
async def get_runtime_profile_presets():
    """
    Get available runtime profile preset templates

    Returns list of available preset template names and their descriptions.
    """
    presets = {
        "security": {
            "name": "security",
            "label": "安全模板",
            "description": "嚴格確認政策、完整品質關卡、保守工具政策",
            "icon": "🛡️"
        },
        "agile": {
            "name": "agile",
            "label": "敏捷模板",
            "description": "最小確認、快速執行、寬鬆工具政策",
            "icon": "⚡"
        },
        "research": {
            "name": "research",
            "label": "研究模板",
            "description": "詳細輸出、引用要求、完整決策日誌",
            "icon": "🔬"
        }
    }
    return {"presets": list(presets.values())}


@router.post(
    "/{workspace_id}/runtime-profile/apply-preset",
    response_model=WorkspaceRuntimeProfile,
    summary="Apply preset template to runtime profile",
    description="""
    Apply a preset template to create or update the workspace runtime profile.

    **Available Presets:**
    - `security`: Strict confirmation policies, complete quality gates, conservative tool policies
    - `agile`: Minimal confirmation, fast execution, relaxed tool policies
    - `research`: Detailed output, citation requirements, complete decision logs

    **Example Request:**
    ```json
    {
        "preset_name": "agile"
    }
    ```

    **Best Practices:**
    1. Use presets as a starting point for new workspaces
    2. Customize the applied preset if needed using `PUT /{workspace_id}/runtime-profile`
    3. Document why you chose a specific preset using `updated_reason`
    """,
    tags=["runtime-profile"],
    responses={
        200: {
            "description": "Preset applied successfully",
            "content": {
                "application/json": {
                    "example": {
                        "default_mode": "execution",
                        "interaction_budget": {
                            "max_questions_per_turn": 0,
                            "assume_defaults": True
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid preset name"},
        404: {"description": "Workspace not found"},
        500: {"description": "Internal server error"}
    }
)
async def apply_runtime_profile_preset(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123"),
    preset_name: str = Body(..., embed=True, description="Preset template name (security, agile, research)", example="agile"),
    updated_by: Optional[str] = Query(None, description="User ID who applied this preset", example="user_456"),
    updated_reason: Optional[str] = Query(None, description="Reason for applying preset", example="Setting up development workspace")
):
    """
    Apply a preset template to workspace runtime profile

    Creates or updates the runtime profile using a preset template.
    """
    try:
        # Verify workspace exists
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        # Get preset template
        preset_templates = get_preset_templates()
        if preset_name not in preset_templates:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid preset name: {preset_name}. Available presets: {', '.join(preset_templates.keys())}"
            )

        # Create profile from preset
        preset_func = preset_templates[preset_name]
        profile = preset_func(workspace_id)

        # Save profile
        profile_store = get_runtime_profile_store()
        updated_profile = profile_store.save_runtime_profile(
            workspace_id=workspace_id,
            profile=profile,
            updated_by=updated_by,
            updated_reason=updated_reason or f"Applied {preset_name} preset template"
        )

        logger.info(f"Applied {preset_name} preset to workspace {workspace_id}")
        return updated_profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to apply preset: {str(e)}")


# ============================================================================
# Control Profile Endpoints
# ============================================================================

@router.get(
    "/{workspace_id}/control-profile",
    response_model=ControlProfile,
    summary="Get workspace control profile",
    description="""
    Get the control profile (knob-based control) configuration for a workspace.

    Control Profile allows users to adjust LLM behavior through intuitive knobs:
    - Intervention Level: How proactive the AI should be
    - Convergence: How quickly to converge to decisions
    - Verbosity: Output density (one-liner to full draft)
    - Retrieval Radius: Scope of information retrieval

    **Returns:**
    - If a profile exists: Returns the configured control profile
    - If no profile exists: Returns default "advisor" preset
    """,
    tags=["control-profile"],
    responses={
        200: {"description": "Control profile retrieved successfully"},
        404: {"description": "Workspace not found"},
        500: {"description": "Internal server error"}
    }
)
async def get_control_profile(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123")
):
    """Get workspace control profile"""
    try:
        # Verify workspace exists
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        profile_store = get_control_profile_store()
        profile = profile_store.get_or_create_default_profile(workspace_id)

        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get control profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get control profile: {str(e)}")


@router.put(
    "/{workspace_id}/control-profile",
    response_model=ControlProfile,
    summary="Update workspace control profile",
    description="""
    Update or create the control profile configuration for a workspace.

    **Request Body:**
    The request body should contain a complete `ControlProfile` object with knob values.

    **Example Request:**
    ```json
    {
        "id": "custom",
        "name": "Custom Profile",
        "knobs": [...],
        "knob_values": {
            "intervention_level": 60,
            "convergence": 50,
            "verbosity": 70,
            "retrieval_radius": 50
        },
        "preset_id": "advisor"
    }
    ```
    """,
    tags=["control-profile"],
    responses={
        200: {"description": "Control profile updated successfully"},
        404: {"description": "Workspace not found"},
        500: {"description": "Internal server error"}
    }
)
async def update_control_profile(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123"),
    profile: ControlProfile = Body(..., description="Control profile configuration"),
    updated_by: Optional[str] = Query(None, description="User ID who updated this profile")
):
    """Update workspace control profile"""
    try:
        # Verify workspace exists
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        profile_store = get_control_profile_store()
        updated_profile = profile_store.save_control_profile(
            workspace_id=workspace_id,
            profile=profile,
            updated_by=updated_by
        )

        return updated_profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update control profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update control profile: {str(e)}")


@router.post(
    "/{workspace_id}/control-profile/compare-preview",
    summary="Compare preview for control profile",
    description="""
    Generate a comparison preview showing output differences between two control profiles.

    This endpoint uses a fast model to generate preview outputs for the same input
    with different control profile settings, allowing users to see the effect of knob adjustments.

    **Request Body:**
    ```json
    {
        "input_text": "我有這些會議記錄",
        "left_profile": {...},
        "right_profile": {...}
    }
    ```

    **Returns:**
    - left_output: Output with left profile
    - right_output: Output with right profile
    - diff_summary: Rule-based difference summary
    - preview_disclaimer: Disclaimer about preview accuracy
    """,
    tags=["control-profile"],
    responses={
        200: {"description": "Comparison preview generated successfully"},
        404: {"description": "Workspace not found"},
        500: {"description": "Internal server error"}
    }
)
async def compare_preview(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123"),
    input_text: str = Body(..., description="User input text for comparison"),
    left_profile: ControlProfile = Body(..., description="Left profile (usually current)"),
    right_profile: ControlProfile = Body(..., description="Right profile (usually new/preset)"),
):
    """
    Compare preview: Show output differences between two control profiles

    v2.4: Uses rule-based diff summary (not LLM-generated) for reliability
    """
    try:
        # Verify workspace exists
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # v2.4: Rule-based difference summary
        def compute_diff_summary(left: ControlProfile, right: ControlProfile) -> str:
            """Rule-based diff summary (not LLM-generated)"""
            diffs = []
            knob_labels = {
                "intervention_level": ("更主動", "更旁觀"),
                "convergence": ("更收斂", "更發散"),
                "verbosity": ("更詳細", "更簡潔"),
                "retrieval_radius": ("更廣檢索", "更窄檢索"),
            }

            for knob_id, (high_label, low_label) in knob_labels.items():
                left_val = left.knob_values.get(knob_id, 50)
                right_val = right.knob_values.get(knob_id, 50)
                delta = right_val - left_val

                if abs(delta) >= 10:  # Only show significant differences
                    label = high_label if delta > 0 else low_label
                    diffs.append(f"{label} ({'+' if delta > 0 else ''}{delta})")

            if not diffs:
                return "Settings difference is minimal"
            return "Right side: " + ", ".join(diffs)

        diff_summary = compute_diff_summary(left_profile, right_profile)

        # Generate preview outputs using compiled profiles
        # Note: This is a simplified preview - full implementation would call LLM
        try:
            from ...services.knob_effect_compiler import KnobEffectCompiler
            from ...services.stores.workspace_runtime_profile_store import WorkspaceRuntimeProfileStore

            runtime_profile_store = WorkspaceRuntimeProfileStore(db_path=store.db_path)
            base_runtime_profile = runtime_profile_store.get_runtime_profile(workspace_id)
            if not base_runtime_profile:
                base_runtime_profile = runtime_profile_store.create_default_profile(workspace_id)

            compiler = KnobEffectCompiler(knobs=left_profile.knobs)
            left_prompt, _, _, _ = compiler.compile(
                control_profile=left_profile,
                base_runtime_profile=base_runtime_profile
            )

            compiler_right = KnobEffectCompiler(knobs=right_profile.knobs)
            right_prompt, _, _, _ = compiler_right.compile(
                control_profile=right_profile,
                base_runtime_profile=base_runtime_profile
            )

            # For now, return prompt previews (actual LLM generation can be added later)
            # TODO: Future enhancement: call fast LLM to generate actual output comparison
            if left_prompt:
                left_output = f"提示詞補丁預覽：\n{left_prompt[:300]}{'...' if len(left_prompt) > 300 else ''}\n\n[注意：這是提示詞差異預覽，非實際 LLM 輸出]"
            else:
                left_output = "[左邊設定：無提示詞變更]"

            if right_prompt:
                right_output = f"提示詞補丁預覽：\n{right_prompt[:300]}{'...' if len(right_prompt) > 300 else ''}\n\n[注意：這是提示詞差異預覽，非實際 LLM 輸出]"
            else:
                right_output = "[右邊設定：無提示詞變更]"

        except Exception as e:
            logger.warning(f"Failed to generate preview prompts: {e}", exc_info=True)
            left_output = "[預覽生成失敗]"
            right_output = "[預覽生成失敗]"

        return {
            "left_output": left_output,
            "right_output": right_output,
            "diff_summary": diff_summary,
            "preview_disclaimer": "預覽顯示提示詞差異，實際輸出可能略有不同",
            "preview_model": "prompt-preview",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate compare preview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate compare preview: {str(e)}")


@router.get(
    "/control-profile/presets",
    summary="Get control profile preset templates",
    description="""
    Get available control profile preset templates.

    Presets provide pre-configured knob values for common use cases:
    - **observer**: Low intervention, organize only
    - **advisor**: Medium-high intervention, proactive suggestions
    - **executor**: High intervention, ready-to-confirm drafts
    """,
    tags=["control-profile"],
    responses={
        200: {"description": "List of available preset templates"}
    }
)
async def get_control_profile_presets():
    """Get available control profile preset templates"""
    presets = [
        {
            "id": "observer",
            "name": "整理模式",
            "description": "只整理資訊，不主動建議",
            "icon": "👁️",
            "knob_values": PRESETS["observer"].knob_values
        },
        {
            "id": "advisor",
            "name": "提案模式",
            "description": "主動提出建議和選項",
            "icon": "💡",
            "knob_values": PRESETS["advisor"].knob_values
        },
        {
            "id": "executor",
            "name": "可直接交付",
            "description": "直接產出可確認的草稿",
            "icon": "🚀",
            "knob_values": PRESETS["executor"].knob_values
        }
    ]
    return {"presets": presets}


# ============================================================================
# Runtime Environment Endpoints
# ============================================================================

@router.get("/{workspace_id}/runtime")
async def get_workspace_runtime(
    workspace_id: str = PathParam(..., description="Workspace ID")
) -> Dict[str, Any]:
    """
    Get runtime configuration for a workspace.

    Returns:
        Dictionary containing:
        - runtime_id: Current runtime ID
        - status: Connection status
        - group_id: Workspace group ID (if exists, for future use)
        - workspace_role: "dispatch" or "cell" (default: "cell")
        - group_runtime: Group-level runtime (if exists)
        - effective_runtime: Effective runtime after priority resolution
    """
    try:
        # Get workspace
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404,
                detail=f"Workspace '{workspace_id}' not found"
            )

        # Get workspace runtime configuration
        # For now, we'll store it in workspace metadata
        workspace_runtime_id = None
        if hasattr(workspace, 'metadata') and workspace.metadata:
            if isinstance(workspace.metadata, dict):
                workspace_runtime_id = workspace.metadata.get('runtime_id')

        # Get group runtime (if exists, for future use)
        group_runtime_id = None
        # TODO: Implement group-level runtime when WorkspaceGroup is available

        # Determine effective runtime (priority: workspace > group > default)
        effective_runtime_id = workspace_runtime_id or group_runtime_id or "local-core"

        # Get runtime status
        runtime_status = "connected"
        if effective_runtime_id != "local-core":
            # Check if external runtime exists and is configured
            # Note: This requires database access, which we'll need to implement
            # For now, return "not_configured" if not local-core
            runtime_status = "not_configured"
            # TODO: Query RuntimeEnvironment table to get actual status

        return {
            "runtime_id": effective_runtime_id,
            "status": runtime_status,
            "group_id": None,  # TODO: Implement when WorkspaceGroup is available
            "workspace_role": "cell",  # Local-Core default is cell
            "group_runtime": group_runtime_id,
            "workspace_runtime": workspace_runtime_id,
            "effective_runtime": effective_runtime_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workspace runtime: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get workspace runtime")


@router.put("/{workspace_id}/runtime")
async def update_workspace_runtime(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: Dict[str, Any] = Body(..., description="Runtime update request")
) -> Dict[str, Any]:
    """
    Update runtime configuration for a workspace.

    Args:
        workspace_id: Workspace ID
        request: Request body containing runtime_id

    Returns:
        Updated runtime configuration
    """
    try:
        runtime_id = request.get("runtime_id")
        if not runtime_id:
            raise HTTPException(
                status_code=400,
                detail="runtime_id is required in request body"
            )

        # Validate runtime_id
        if runtime_id != "local-core":
            # TODO: Check if runtime exists and user has access
            # This requires database access to RuntimeEnvironment table
            pass

        # Get workspace
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404,
                detail=f"Workspace '{workspace_id}' not found"
            )

        # Update workspace runtime
        # Store in metadata for now (can be moved to dedicated field later)
        if not hasattr(workspace, 'metadata') or not workspace.metadata:
            workspace.metadata = {}
        elif not isinstance(workspace.metadata, dict):
            workspace.metadata = {}

        workspace.metadata['runtime_id'] = runtime_id

        # Update workspace
        updated = store.update_workspace(workspace)

        # Get effective runtime
        effective_runtime_id = runtime_id

        # Get runtime status
        runtime_status = "connected"
        if effective_runtime_id != "local-core":
            runtime_status = "not_configured"
            # TODO: Query RuntimeEnvironment table to get actual status

        return {
            "success": True,
            "runtime_id": effective_runtime_id,
            "effective_runtime": effective_runtime_id,
            "status": runtime_status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update workspace runtime: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update workspace runtime")


# ============================================================================
# Mount Sub-Routers
# ============================================================================
# Sub-routers are loaded via pack registry
# See backend/packs/workspace-pack.yaml and backend/features/workspace/

# Import and mount workspace governance router
from . import workspace_governance
router.include_router(workspace_governance.router)

# Import pinned playbooks store
from ...services.stores.workspace_pinned_playbooks_store import WorkspacePinnedPlaybooksStore
from ...services.mindscape_store import MindscapeStore
_store = MindscapeStore()
pinned_playbooks_store = WorkspacePinnedPlaybooksStore(_store.db_path)


@router.get("/{workspace_id}/pinned-playbooks", response_model=List[Dict[str, Any]])
async def get_pinned_playbooks(
    workspace_id: str = PathParam(..., description="Workspace ID")
):
    """
    Get all pinned playbooks for a workspace
    """
    try:
        pinned = pinned_playbooks_store.list_pinned_playbooks(workspace_id)
        return pinned
    except Exception as e:
        logger.error(f"Failed to get pinned playbooks for workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/pinned-playbooks", response_model=Dict[str, Any], status_code=201)
async def pin_playbook(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: Dict[str, Any] = Body(...)
):
    """
    Pin a playbook to a workspace
    """
    try:
        playbook_code = request.get("playbook_code")
        if not playbook_code:
            raise HTTPException(status_code=400, detail="playbook_code is required")

        pinned_by = request.get("pinned_by")
        result = pinned_playbooks_store.pin_playbook(workspace_id, playbook_code, pinned_by)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pin playbook {request.get('playbook_code')} to workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workspace_id}/pinned-playbooks/{playbook_code}", status_code=204)
async def unpin_playbook(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = PathParam(..., description="Playbook code")
):
    """
    Unpin a playbook from a workspace
    """
    try:
        success = pinned_playbooks_store.unpin_playbook(workspace_id, playbook_code)
        if not success:
            raise HTTPException(status_code=404, detail="Playbook not pinned in this workspace")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unpin playbook {playbook_code} from workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

