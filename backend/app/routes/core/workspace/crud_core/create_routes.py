
import asyncio
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import ValidationError

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.models.workspace import (
    CreateWorkspaceRequest,
    LaunchStatus,
    Workspace,
    WorkspaceVisibility,
)
from backend.app.services.storage_path_resolver import StoragePathResolver
from backend.app.services.storage_path_validator import StoragePathValidator
from backend.app.services.workspace_welcome_service import WorkspaceWelcomeService

from .state import _utc_now, logger, store

router = APIRouter()

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

        # Workspace locale is content/execution policy, not Workbench UI state.
        from backend.app.services.workspace_locale_seed import (
            resolve_workspace_default_locale,
        )

        default_locale = await asyncio.to_thread(
            resolve_workspace_default_locale,
            explicit_locale=request.default_locale,
            owner_user_id=owner_user_id,
            profile_store=store,
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
            execution_mode=request.execution_mode,
            expected_artifacts=request.expected_artifacts,
            execution_priority=request.execution_priority,
            sandbox_config=request.sandbox_config,
            workspace_blueprint=request.workspace_blueprint,
            starter_kit_type=request.starter_kit_type,
            storage_config={
                "bucket_strategy": "playbook_code",
                "naming_rule": "slug-v{version}-{timestamp}.{ext}",
            },
            visibility=(
                request.visibility
                if getattr(request, "visibility", None)
                else WorkspaceVisibility.PRIVATE
            ),
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )

        created = await asyncio.to_thread(store.create_workspace, workspace)

        try:
            from backend.app.services.host_resources.allocation_blueprints import (
                apply_default_host_resource_blueprint_to_workspace,
            )

            await asyncio.to_thread(
                apply_default_host_resource_blueprint_to_workspace,
                workspace_id=created.id,
                owner_user_id=owner_user_id,
                actor_id=owner_user_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to apply default host resource blueprint for workspace %s: %s",
                created.id,
                exc,
            )

        # Auto-register background routine for state sync (skip for system workspaces)
        # System workspaces are for validation/testing and should not have background routines
        if not getattr(created, "is_system", False):
            try:
                from backend.app.models.workspace import BackgroundRoutine
                from backend.app.services.stores.postgres.background_routines_store import (
                    PostgresBackgroundRoutinesStore,
                )

                routines_store = PostgresBackgroundRoutinesStore()

                # Check if state sync routine already exists for this workspace
                existing = await asyncio.to_thread(
                    routines_store.get_background_routine_by_playbook,
                    workspace_id=created.id,
                    playbook_code="system_mindscape_state_sync",
                )

                if not existing:
                    # Create background routine for state sync (runs daily at 2 AM)
                    routine = BackgroundRoutine(
                        id=str(uuid.uuid4()),
                        workspace_id=created.id,
                        playbook_code="system_mindscape_state_sync",
                        schedule="0 2 * * *",  # Daily at 2 AM
                        enabled=True,
                        created_at=_utc_now(),
                        updated_at=_utc_now(),
                    )
                    await asyncio.to_thread(
                        routines_store.create_background_routine, routine
                    )
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
            timestamp=_utc_now(),
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
        await asyncio.to_thread(store.create_event, event)

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
            # Get or create the default thread for the welcome message
            from backend.features.workspace.chat.streaming.generator import (
                _get_or_create_default_thread,
            )

            default_thread_id = _get_or_create_default_thread(created.id, store)

            welcome_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=_utc_now(),
                actor=EventActor.ASSISTANT,
                channel="local_workspace",
                profile_id=owner_user_id,
                project_id=request.primary_project_id,
                workspace_id=created.id,
                thread_id=default_thread_id,
                event_type=EventType.MESSAGE,
                payload={
                    "message": welcome_message,
                    "is_welcome": True,
                    "suggestions": suggestions,
                },
                entity_ids=[],
                metadata={"is_cold_start": True},
            )
            await asyncio.to_thread(store.create_event, welcome_event)

            # Update thread statistics
            try:
                # Use COUNT query to accurately calculate message count
                message_count = await asyncio.to_thread(
                    store.events.count_messages_by_thread,
                    workspace_id=created.id,
                    thread_id=default_thread_id,
                )
                await asyncio.to_thread(
                    store.conversation_threads.update_thread,
                    thread_id=default_thread_id,
                    last_message_at=_utc_now(),
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
