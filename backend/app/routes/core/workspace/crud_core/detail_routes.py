
import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Path as PathParam
from pydantic import ValidationError

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.models.workspace import UpdateWorkspaceRequest, Workspace
from backend.app.services.storage_path_validator import StoragePathValidator

from ..utils import ensure_workspace_launch_status
from .state import _utc_now, logger, store

router = APIRouter()

@router.get("/{workspace_id}")
async def get_workspace(workspace_id: str = PathParam(..., description="Workspace ID")):
    """
    Get workspace by ID

    Returns workspace details including configuration, metadata, and associated intent.
    Includes workspace_blueprint for Launchpad display.
    """
    import time

    request_id = f"req-{int(time.time() * 1000)}-{id(asyncio.current_task())}"
    logger.info(f"[{request_id}] GET /workspaces/{workspace_id} - Request started")

    try:
        import time
        t_start = time.time()
        logger.info(f"[{request_id}] Getting workspace from store...")
        workspace = await store.get_workspace(workspace_id)
        t_store = time.time()
        logger.info(
            f"[{request_id}] Workspace retrieved: {workspace.id if workspace else 'None'} in {t_store - t_start:.3f}s"
        )

        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Reconcile launch_status
        await ensure_workspace_launch_status(workspace_id, workspace)
        t_launch = time.time()
        logger.info(f"[{request_id}] Launch status checked in {t_launch - t_store:.3f}s")

        associated_intent = None
        if workspace.primary_project_id:
            try:
                from backend.app.services.stores.postgres.intents_store import (
                    PostgresIntentsStore,
                )

                intents_store = PostgresIntentsStore()
                intent = await asyncio.to_thread(
                    intents_store.get_intent, workspace.primary_project_id
                )
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

        t_intent = time.time()
        logger.info(f"[{request_id}] Intent checked in {t_intent - t_launch:.3f}s")

        workspace_dict = workspace.model_dump()
        if associated_intent:
            workspace_dict["associated_intent"] = associated_intent

        t_dump = time.time()
        logger.info(f"[{request_id}] Pydantic dump took {t_dump - t_intent:.3f}s")

        logger.info(f"[{request_id}] Returning workspace data (total {t_dump - t_start:.3f}s)")
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
            f"Updating workspace {workspace_id} with request: {request.model_dump(exclude_unset=True)}"
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
        provided_fields = request.model_dump(exclude_unset=True)
        request_dict = request.model_dump(exclude_unset=False)
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

        # Handle metadata merge-update (governance features, SGR settings, etc.)
        if hasattr(request, "metadata") and request.metadata is not None:
            existing_meta = workspace.metadata or {}
            existing_meta.update(request.metadata)
            workspace.metadata = existing_meta
            logger.info(
                f"Merged metadata for workspace {workspace_id}: keys={list(request.metadata.keys())}"
            )

        # Handle workspace_blueprint update (instruction editor)
        if (
            hasattr(request, "workspace_blueprint")
            and request.workspace_blueprint is not None
        ):
            existing_bp = workspace.workspace_blueprint
            new_bp = request.workspace_blueprint
            if existing_bp:
                # Merge: update only provided fields
                if new_bp.instruction is not None:
                    existing_bp.instruction = new_bp.instruction
                if new_bp.brief is not None:
                    existing_bp.brief = new_bp.brief
                workspace.workspace_blueprint = existing_bp
            else:
                workspace.workspace_blueprint = new_bp
            logger.info(f"Updated workspace_blueprint for workspace {workspace_id}")

        # Handle visibility update
        if hasattr(request, "visibility") and request.visibility is not None:
            workspace.visibility = request.visibility
            logger.info(
                f"Updated visibility for workspace {workspace_id}: {request.visibility}"
            )

        # If path changed, record warning to event system
        if storage_path_changed:
            warning_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=_utc_now(),
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
            await asyncio.to_thread(store.create_event, warning_event)

        updated = await store.update_workspace(workspace)
        logger.info(
            f"Workspace {workspace_id} updated successfully. Storage path: {updated.storage_base_path}, Artifacts dir: {updated.artifacts_dir}"
        )

        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=_utc_now(),
            actor=EventActor.SYSTEM,
            channel="api",
            profile_id=workspace.owner_user_id,
            project_id=workspace.primary_project_id,
            workspace_id=workspace_id,
            event_type=EventType.PROJECT_UPDATED,
            payload={
                "workspace_id": workspace_id,
                "updated_fields": request.model_dump(exclude_unset=True),
            },
            entity_ids=[],
            metadata={},
        )
        await asyncio.to_thread(store.create_event, event)

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

        await asyncio.to_thread(store.delete_workspace, workspace_id)
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete workspace: {str(e)}"
        )
