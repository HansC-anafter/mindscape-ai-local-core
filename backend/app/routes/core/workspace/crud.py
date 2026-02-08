import logging
import uuid
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any, Dict

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Query,
    Body,
)
from pydantic import ValidationError

from ....models.workspace import (
    Workspace,
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    LaunchStatus,
)
from ....models.mindscape import MindEvent, EventType, EventActor
from ....services.mindscape_store import MindscapeStore
from ....services.storage_path_validator import StoragePathValidator
from ....services.storage_path_resolver import StoragePathResolver
from ....services.workspace_welcome_service import WorkspaceWelcomeService

from .utils import ensure_workspace_launch_status

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()


@router.get("/", response_model=List[Workspace])
async def list_workspaces(
    owner_user_id: str = Query(..., description="Owner user ID"),
    primary_project_id: Optional[str] = Query(
        None, description="Filter by primary project ID"
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of workspaces"),
    include_system: bool = Query(
        False, description="Include system workspaces (validation, testing, etc.)"
    ),
    group_id: Optional[str] = Query(
        None, description="Group ID filter (Cloud only, ignored in local-core)"
    ),
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
            limit=limit,
        )
        # Filter out system workspaces unless explicitly requested
        if not include_system:
            workspaces = [
                ws for ws in workspaces if not getattr(ws, "is_system", False)
            ]
        # Note: group_id parameter is ignored in local-core (backward compatibility for Cloud)
        return workspaces
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list workspaces: {str(e)}"
        )


@router.post("/", response_model=Workspace, status_code=201)
async def create_workspace(
    request: CreateWorkspaceRequest = Body(...),
    owner_user_id: str = Query(..., description="Owner user ID"),
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
        if hasattr(request, "storage_base_path") and request.storage_base_path:
            requested_path_str = request.storage_base_path.strip()

            # Use StoragePathValidator service for validation
            is_valid, error_message, _ = (
                StoragePathValidator.validate_and_check_host_path(requested_path_str)
            )
            if not is_valid:
                raise HTTPException(status_code=400, detail=error_message)

            requested_path = Path(requested_path_str).expanduser().resolve()

            if allowed_dirs:
                # When allowed directories configured, must validate
                if not StoragePathValidator.validate_path_in_allowed_directories(
                    requested_path, allowed_dirs
                ):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Specified path {request.storage_base_path} is not within allowed directories",
                    )
            else:
                # When no allowed directories configured, allow manual specification (but log warning)
                logger.warning(
                    f"User manually specified path without allowed directories config: {request.storage_base_path}"
                )

            storage_base_path = str(requested_path)

            # Generate full path: <base_path>/Mindscape/<workspace_name>/
            workspace_storage_path = (
                Path(storage_base_path).expanduser() / "Mindscape" / request.title
            )
            workspace_storage_path = workspace_storage_path.resolve()

            # Security check: validate final path is still within allowed directories (prevent directory traversal)
            if (
                allowed_dirs
                and not StoragePathValidator.validate_path_in_allowed_directories(
                    workspace_storage_path, allowed_dirs
                )
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Generated path {workspace_storage_path} is not within allowed directories, security risk may exist",
                )

            # Create directory (if not exists)
            workspace_storage_path.mkdir(parents=True, exist_ok=True)

            # Verify directory is writable
            if not os.access(workspace_storage_path, os.W_OK):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot write to directory: {workspace_storage_path}, please check permissions",
                )

            workspace_storage_path_str = str(workspace_storage_path)
        else:
            # No storage path specified - automatically generate a default path for the workspace
            # Uses unified solution: env var > allowed directories > project data directory
            default_base = await StoragePathResolver.get_default_storage_path(store)

            if default_base:
                # Generate workspace-specific path: <base>/<workspace_title>/
                # Sanitize workspace title for use in file path
                safe_title = re.sub(r"[^\w\s-]", "", request.title).strip()
                safe_title = re.sub(
                    r"[-\s]+", "-", safe_title
                )  # Replace spaces and multiple dashes with single dash
                if not safe_title:
                    safe_title = f"workspace-{uuid.uuid4().hex[:8]}"

                workspace_storage_path = Path(default_base).expanduser() / safe_title
                workspace_storage_path = workspace_storage_path.resolve()

                # Create directory (if not exists)
                try:
                    workspace_storage_path.mkdir(parents=True, exist_ok=True)

                    # Verify directory is writable
                    if not os.access(workspace_storage_path, os.W_OK):
                        logger.warning(
                            f"Cannot write to auto-generated directory: {workspace_storage_path}, workspace will be created without storage path"
                        )
                        workspace_storage_path_str = None
                    else:
                        workspace_storage_path_str = str(workspace_storage_path)
                        logger.info(
                            f"Auto-generated workspace storage path: {workspace_storage_path_str}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to create auto-generated workspace directory {workspace_storage_path}: {e}, workspace will be created without storage path"
                    )
                    workspace_storage_path_str = None

        # Create Workspace (with storage configuration)
        # Get default_locale from request, or fallback to system settings
        if request.default_locale:
            default_locale = request.default_locale
        else:
            from ....services.system_settings_store import SystemSettingsStore

            settings_store = SystemSettingsStore(db_path=store.db_path)
            language_setting = settings_store.get_setting("default_language")
            default_locale = (
                language_setting.value
                if language_setting and language_setting.value
                else "zh-TW"
            )

        workspace = Workspace(
            id=str(uuid.uuid4()),
            title=request.title,
            description=request.description,
            is_system=getattr(request, "is_system", False),
            workspace_type=(
                request.workspace_type
                if hasattr(request, "workspace_type") and request.workspace_type
                else None
            ),
            owner_user_id=owner_user_id,
            primary_project_id=request.primary_project_id,
            default_playbook_id=request.default_playbook_id,
            default_locale=default_locale,
            storage_base_path=workspace_storage_path_str,
            artifacts_dir=getattr(request, "artifacts_dir", None) or "artifacts",
            uploads_dir="uploads",
            storage_config={
                "bucket_strategy": "playbook_code",
                "naming_rule": "slug-v{version}-{timestamp}.{ext}",
            },
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        created = store.create_workspace(workspace)

        # Auto-register background routine for state sync (skip for system workspaces)
        # System workspaces are for validation/testing and should not have background routines
        if not getattr(created, "is_system", False):
            try:
                from ....models.workspace import BackgroundRoutine
                from ....services.stores.background_routines_store import (
                    BackgroundRoutinesStore,
                )

                routines_store = BackgroundRoutinesStore(db_path=store.db_path)

                # Check if state sync routine already exists for this workspace
                existing = routines_store.get_background_routine_by_playbook(
                    workspace_id=created.id, playbook_code="system_mindscape_state_sync"
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
                        updated_at=datetime.utcnow(),
                    )
                    routines_store.create_background_routine(routine)
                    logger.info(
                        f"Auto-registered state sync background routine for workspace {created.id}"
                    )
            except Exception as e:
                logger.warning(f"Failed to register state sync background routine: {e}")
        else:
            logger.debug(
                f"Skipping background routine registration for system workspace {created.id}"
            )

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
            metadata={},
        )
        store.create_event(event)

        locale = (
            created.default_locale
            if hasattr(created, "default_locale") and created.default_locale
            else default_locale
        )
        welcome_message, suggestions = (
            await WorkspaceWelcomeService.generate_welcome_message(
                created, owner_user_id, store, locale=locale
            )
        )
        if welcome_message:
            # 🆕 Get or create default thread for welcome message
            from backend.features.workspace.chat.streaming.generator import (
                _get_or_create_default_thread,
            )

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
                    "suggestions": suggestions,
                },
                entity_ids=[],
                metadata={"is_cold_start": True},
            )
            store.create_event(welcome_event)

            # 🆕 Update thread statistics
            try:
                # Use COUNT query to accurately calculate message count
                message_count = store.events.count_messages_by_thread(
                    workspace_id=created.id, thread_id=default_thread_id
                )
                store.conversation_threads.update_thread(
                    thread_id=default_thread_id,
                    last_message_at=datetime.utcnow(),
                    message_count=message_count,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to update thread statistics for welcome message: {e}"
                )

        return created
    except ValidationError as e:
        logger.error(f"Validation error when creating workspace: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Failed to create workspace: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to create workspace: {str(e)}"
        )


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: str = PathParam(..., description="Workspace ID")):
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
        workspace = await store.get_workspace(workspace_id)
        logger.info(
            f"[{request_id}] Workspace retrieved: {workspace.id if workspace else 'None'}"
        )

        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Reconcile launch_status
        await ensure_workspace_launch_status(workspace_id, workspace)

        associated_intent = None
        if workspace.primary_project_id:
            try:
                from ....services.stores.intents_store import IntentsStore

                intents_store = IntentsStore(store.db_path)
                intent = intents_store.get_intent(workspace.primary_project_id)
                if intent:
                    associated_intent = {
                        "id": intent.id,
                        "title": intent.title,
                        "tags": intent.tags,
                        "status": intent.status.value,
                        "priority": intent.priority.value,
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
        raise HTTPException(
            status_code=500, detail=f"Failed to get workspace: {str(e)}"
        )


@router.put("/{workspace_id}", response_model=Workspace)
async def update_workspace(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: UpdateWorkspaceRequest = Body(...),
):
    """
    Update an existing workspace

    Updates workspace fields. Only provided fields will be updated.
    """
    try:
        logger.info(
            f"Updating workspace {workspace_id} with request: {request.dict(exclude_unset=True)}"
        )
        workspace = await store.get_workspace(workspace_id)
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
        if "mode" in request_dict:
            workspace.mode = request.mode
        if (
            hasattr(request, "playbook_storage_config")
            and request.playbook_storage_config is not None
        ):
            workspace.playbook_storage_config = request.playbook_storage_config

        # Handle storage path update (if these fields exist in request)
        if (
            hasattr(request, "storage_base_path")
            and request.storage_base_path is not None
        ):
            if request.storage_base_path != old_storage_base_path:
                storage_path_changed = True
                # Validate new path using StoragePathValidator service
                is_valid, error_message, _ = (
                    StoragePathValidator.validate_and_check_host_path(
                        request.storage_base_path
                    )
                )
                if not is_valid:
                    raise HTTPException(status_code=400, detail=error_message)

                new_path = Path(request.storage_base_path).expanduser().resolve()

                if not new_path.exists():
                    try:
                        new_path.mkdir(parents=True, exist_ok=True)
                        logger.info(f"Created storage directory: {new_path}")
                        # Verify directory was actually created
                        if not new_path.exists():
                            logger.warning(
                                f"Directory creation reported success but path does not exist: {new_path}"
                            )
                            raise HTTPException(
                                status_code=400,
                                detail=f"Failed to create storage path {new_path}. Directory may not be accessible from container.",
                            )
                    except PermissionError as e:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Permission denied when creating storage path {new_path}: {str(e)}. Please check Docker Desktop file sharing settings.",
                        )
                    except Exception as e:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Failed to create storage path {new_path}: {str(e)}",
                        )
                if not os.access(new_path, os.W_OK):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Storage path is not writable: {new_path}. Please check directory permissions and Docker Desktop file sharing settings.",
                    )
                # Validate path is within allowed directories
                allowed_dirs = StoragePathValidator.get_allowed_directories()
                if (
                    allowed_dirs
                    and not StoragePathValidator.validate_path_in_allowed_directories(
                        new_path, allowed_dirs
                    )
                ):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Storage path {new_path} is not within allowed directories. This may indicate a security issue.",
                    )
                workspace.storage_base_path = request.storage_base_path
                logger.warning(
                    f"Workspace {workspace_id} storage_base_path changed from {old_storage_base_path} to {request.storage_base_path}. "
                    "Existing artifacts may not be automatically found. Consider migrating artifacts manually."
                )

        if hasattr(request, "artifacts_dir") and request.artifacts_dir is not None:
            if request.artifacts_dir != old_artifacts_dir:
                storage_path_changed = True
                workspace.artifacts_dir = request.artifacts_dir
                logger.warning(
                    f"Workspace {workspace_id} artifacts_dir changed from {old_artifacts_dir} to {request.artifacts_dir}. "
                    "Existing artifacts may not be automatically found. Consider migrating artifacts manually."
                )

        # Handle playbook_storage_config update
        if (
            hasattr(request, "playbook_storage_config")
            and request.playbook_storage_config is not None
        ):
            # Validate playbook storage config paths
            for playbook_code, config in request.playbook_storage_config.items():
                if not isinstance(config, dict):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid playbook_storage_config for {playbook_code}: must be a dict",
                    )
                base_path = config.get("base_path")
                if base_path:
                    # Validate path using StoragePathValidator service
                    is_valid, error_message, _ = (
                        StoragePathValidator.validate_and_check_host_path(base_path)
                    )
                    if not is_valid:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Playbook storage path {base_path} for {playbook_code}: {error_message}",
                        )

                    new_path = Path(base_path).expanduser().resolve()

                    if not new_path.exists():
                        try:
                            new_path.mkdir(parents=True, exist_ok=True)
                            logger.info(
                                f"Created playbook storage directory: {new_path}"
                            )
                        except Exception as e:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Failed to create playbook storage path {new_path} for {playbook_code}: {str(e)}",
                            )
                    if not os.access(new_path, os.W_OK):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Playbook storage path is not writable: {new_path} for {playbook_code}. Please check directory permissions.",
                        )
                    # Validate path is within allowed directories
                    allowed_dirs = StoragePathValidator.get_allowed_directories()
                    if (
                        allowed_dirs
                        and not StoragePathValidator.validate_path_in_allowed_directories(
                            new_path, allowed_dirs
                        )
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Playbook storage path {new_path} for {playbook_code} is not within allowed directories. This may indicate a security issue.",
                        )
            workspace.playbook_storage_config = request.playbook_storage_config
            logger.info(f"Updated playbook_storage_config for workspace {workspace_id}")

        # Handle execution mode settings
        if hasattr(request, "execution_mode") and request.execution_mode is not None:
            workspace.execution_mode = request.execution_mode
            logger.info(
                f"Updated execution_mode for workspace {workspace_id}: {request.execution_mode}"
            )
        if (
            hasattr(request, "expected_artifacts")
            and request.expected_artifacts is not None
        ):
            workspace.expected_artifacts = request.expected_artifacts
            logger.info(
                f"Updated expected_artifacts for workspace {workspace_id}: {request.expected_artifacts}"
            )
        if (
            hasattr(request, "execution_priority")
            and request.execution_priority is not None
        ):
            workspace.execution_priority = request.execution_priority
            logger.info(
                f"Updated execution_priority for workspace {workspace_id}: {request.execution_priority}"
            )
        if (
            hasattr(request, "capability_profile")
            and request.capability_profile is not None
        ):
            workspace.capability_profile = request.capability_profile
            logger.info(
                f"Updated capability_profile for workspace {workspace_id}: {request.capability_profile}"
            )

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
                    "new_artifacts_dir": workspace.artifacts_dir,
                },
                entity_ids=[workspace_id],
                metadata={"is_storage_path_change": True},
            )
            store.create_event(warning_event)

        updated = await store.update_workspace(workspace)
        logger.info(
            f"Workspace {workspace_id} updated successfully. Storage path: {updated.storage_base_path}, Artifacts dir: {updated.artifacts_dir}"
        )

        event = MindEvent(
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
                "updated_fields": request.dict(exclude_unset=True),
            },
            entity_ids=[],
            metadata={},
        )
        store.create_event(event)

        return updated
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update workspace: {str(e)}"
        )


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str = PathParam(..., description="Workspace ID")
):
    """
    Delete a workspace

    Permanently deletes the workspace and all associated data.
    """
    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        store.delete_workspace(workspace_id)
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete workspace: {str(e)}"
        )


@router.patch("/{workspace_id}/playbook-auto-exec-config", response_model=Workspace)
async def update_playbook_auto_exec_config(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = Body(..., description="Playbook code"),
    confidence_threshold: Optional[float] = Body(
        None, description="Confidence threshold (0.0-1.0)"
    ),
    auto_execute: Optional[bool] = Body(None, description="Enable auto-execute"),
):
    """
    Update playbook auto-execution configuration

    Sets the confidence threshold and auto-execute flag for a specific playbook in this workspace.
    """
    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Initialize config if not exists
        if workspace.playbook_auto_execution_config is None:
            workspace.playbook_auto_execution_config = {}

        # Update or create playbook config
        if playbook_code not in workspace.playbook_auto_execution_config:
            workspace.playbook_auto_execution_config[playbook_code] = {}

        if confidence_threshold is not None:
            workspace.playbook_auto_execution_config[playbook_code][
                "confidence_threshold"
            ] = confidence_threshold
        if auto_execute is not None:
            workspace.playbook_auto_execution_config[playbook_code][
                "auto_execute"
            ] = auto_execute

        updated = await store.update_workspace(workspace)
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update playbook auto-exec config: {str(e)}",
        )
