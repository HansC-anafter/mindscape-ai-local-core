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
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path as PathParam, Query, Body
from pydantic import ValidationError

from ...models.workspace import (
    Workspace,
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest
)
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


# ============================================================================
# Storage Path Helper Functions
# ============================================================================
# Note: Path validation logic is in storage_path_validator service
# Import here to keep workspace.py focused on CRUD operations
from ...services.storage_path_validator import StoragePathValidator


def _validate_path_in_allowed_directories(
    path: Path,
    allowed_directories: List[str]
) -> bool:
    """
    Validate path is within allowed directories (prevent directory traversal)

    Uses Path.resolve() and validates resolved_path is under allowed directories

    Args:
        path: Path to validate
        allowed_directories: List of allowed directories

    Returns:
        True if path is within allowed directories, False otherwise
    """
    resolved_path = path.resolve()

    for allowed_dir in allowed_directories:
        allowed_path = Path(allowed_dir).expanduser().resolve()

        # Check if resolved_path is under allowed_path
        try:
            # Python 3.9+ use is_relative_to
            if resolved_path.is_relative_to(allowed_path):
                return True
        except AttributeError:
            # Python < 3.9 manual check
            try:
                resolved_path.relative_to(allowed_path)
                return True
            except ValueError:
                continue

    return False


def _get_allowed_directories() -> List[str]:
    """
    Get allowed directories list

    Data source priority (per design requirements):
    1. Environment variable LOCAL_FS_ALLOWED_DIRS (comma-separated)
    2. ToolConnections (read local_filesystem tool config.allowed_directories from tool_connections table)
    3. ToolRegistry (read local_filesystem tool endpoint from tool registry, as fallback)

    Returns:
        List of allowed directories
    """
    allowed_dirs = []

    # 1. Read from environment variable (priority)
    env_dirs = os.getenv("LOCAL_FS_ALLOWED_DIRS", "")
    if env_dirs:
        allowed_dirs.extend([d.strip() for d in env_dirs.split(",") if d.strip()])

    # 2. Read from ToolConnections (per design, read config.allowed_directories from tool_connections)
    try:
        from ...services.tool_connection_store import ToolConnectionStore
        tool_connection_store = ToolConnectionStore()
        # get_connections_by_tool_type requires profile_id, but we're reading system-wide config
        # For now, try to get connections for default-user profile
        try:
            connections = tool_connection_store.get_connections_by_tool_type(
                profile_id="default-user",
                tool_type="local_filesystem"
            )
            # Filter for active connections only
            connections = [conn for conn in connections if conn.is_active]
        except Exception as profile_error:
            logger.debug(f"Failed to get connections for default-user profile: {profile_error}")
            connections = []

        seen_dirs = set(allowed_dirs)
        for connection in connections:
            # Read allowed_directories from config
            if connection.config and isinstance(connection.config, dict):
                allowed_dirs_config = connection.config.get("allowed_directories", [])
                if isinstance(allowed_dirs_config, list):
                    for dir_path in allowed_dirs_config:
                        if isinstance(dir_path, str) and dir_path.strip():
                            try:
                                resolved_path = Path(dir_path).expanduser().resolve()
                                if resolved_path.exists() and resolved_path.is_dir():
                                    dir_str = str(resolved_path)
                                    if dir_str not in seen_dirs:
                                        allowed_dirs.append(dir_str)
                                        seen_dirs.add(dir_str)
                            except Exception as e:
                                logger.debug(f"Invalid directory path in tool_connection config: {dir_path}, error: {e}")
                                pass
    except Exception as e:
        logger.warning(f"Failed to read from ToolConnections: {e}")

    # 3. Read from ToolRegistry (as fallback, extract from tool endpoint)
    if not allowed_dirs:
        try:
            from ...services.tool_registry import ToolRegistryService
            tool_registry = ToolRegistryService()
            tools = tool_registry.get_tools(enabled_only=False)

            # Filter local_filesystem tools, extract directory from endpoint
            seen_dirs = set(allowed_dirs)
            for tool in tools:
                if tool.provider == "local_filesystem" and tool.endpoint:
                    # Endpoint may be a directory path
                    try:
                        endpoint_path = Path(tool.endpoint).expanduser().resolve()
                        if endpoint_path.exists() and endpoint_path.is_dir():
                            dir_str = str(endpoint_path)
                            if dir_str not in seen_dirs:
                                allowed_dirs.append(dir_str)
                                seen_dirs.add(dir_str)
                    except Exception:
                        # endpoint is not valid path, skip
                        pass
        except Exception as e:
            logger.warning(f"Failed to read from ToolRegistry: {e}")

    return list(set(allowed_dirs))


async def _get_default_storage_path(store: MindscapeStore) -> Optional[str]:
    """
    Get default storage path for workspace creation

    Priority order:
    1. Environment variable WORKSPACE_STORAGE_BASE_PATH (for unified deployment)
    2. First allowed directory from Local File System configuration
    3. Project data directory (./data/workspaces) as fallback

    Security requirement: must validate path is within allowed directories (if configured)

    Args:
        store: MindscapeStore instance

    Returns:
        Path string of default storage directory, or None if not available
    """
    # 1. Check environment variable first (unified solution for open-source deployment)
    env_base_path = os.getenv("WORKSPACE_STORAGE_BASE_PATH")
    if env_base_path:
        env_path = Path(env_base_path).expanduser().resolve()
        if env_path.exists() and env_path.is_dir() and os.access(env_path, os.W_OK):
            logger.info(f"Using WORKSPACE_STORAGE_BASE_PATH from environment: {env_path}")
            return str(env_path)
        else:
            logger.warning(f"WORKSPACE_STORAGE_BASE_PATH is set but invalid or not writable: {env_path}")

    # 2. Check allowed directories from configuration
    allowed_dirs = _get_allowed_directories()
    if allowed_dirs:
        # Verify first directory exists and is accessible
        first_dir = Path(allowed_dirs[0]).expanduser().resolve()
        if first_dir.exists() and first_dir.is_dir():
            # Validate path is within allowed directories (even though it's the first directory itself, validate for consistency)
            if _validate_path_in_allowed_directories(first_dir, allowed_dirs):
                logger.info(f"Using first allowed directory: {first_dir}")
                return str(first_dir)
            else:
                logger.warning(f"Directory {first_dir} failed validation")
        else:
            logger.warning(f"Invalid allowed directory: {first_dir}")

    # 3. Fallback to project data directory (always available, mounted in docker-compose.yml)
    # This ensures workspaces can be created even without user configuration
    project_data_dir = Path(__file__).parent.parent.parent.parent / "data" / "workspaces"
    try:
        project_data_dir.mkdir(parents=True, exist_ok=True)
        if os.access(project_data_dir, os.W_OK):
            logger.info(f"Using project data directory as fallback: {project_data_dir}")
            return str(project_data_dir.resolve())
    except Exception as e:
        logger.warning(f"Failed to use project data directory {project_data_dir}: {e}")

    logger.info("No default storage path available, user must specify manually")
    return None


async def _generate_welcome_message(workspace: Workspace, profile_id: str, store: MindscapeStore, locale: str = "en") -> tuple[str, list[str]]:
    """
    Generate welcome message and initial suggestions for a new workspace

    Uses LLM to generate personalized welcome message with workspace namespace,
    intents, and available capabilities for cold start guidance.

    Args:
        workspace: Workspace object
        profile_id: User profile ID
        store: MindscapeStore instance
        locale: Locale for i18n (default: "en")

    Returns:
        (welcome_message, suggestions_list)
    """
    try:
        i18n = get_i18n_service(default_locale=locale)

        profile = store.get_profile(profile_id)
        onboarding_complete = False
        if profile and profile.onboarding_state:
            onboarding_complete = profile.onboarding_state.get('task3_completed', False)

        # For cold start (new workspace), use LLM to generate personalized welcome message
        if not onboarding_complete:
            try:
                from backend.app.services.conversation.context_builder import ContextBuilder
                from backend.app.services.conversation.qa_response_generator import QAResponseGenerator
                from backend.app.services.stores.timeline_items_store import TimelineItemsStore
                from backend.app.capabilities.core_llm.services.generate import run as generate_text
                from backend.app.services.system_settings_store import SystemSettingsStore

                timeline_items_store = TimelineItemsStore(store.db_path)
                qa_generator = QAResponseGenerator(
                    store=store,
                    timeline_items_store=timeline_items_store,
                    default_locale=locale
                )

                # Build context with workspace namespace, intents, and capabilities
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
                    timeline_items_store=timeline_items_store,
                    model_name=model_name
                )
                context = await context_builder.build_qa_context(
                    workspace_id=workspace.id,
                    message="",
                    profile_id=profile_id,
                    workspace=workspace,
                    hours=0  # No history for new workspace
                )

                # Get available playbooks/capabilities
                available_playbooks = []
                try:
                    from backend.app.services.playbook_loader import PlaybookLoader
                    playbook_loader = PlaybookLoader()
                    file_playbooks = playbook_loader.load_all_playbooks()

                    for pb in file_playbooks:
                        metadata = pb.metadata if hasattr(pb, 'metadata') else None
                        if metadata and metadata.playbook_code:
                            available_playbooks.append({
                                'playbook_code': metadata.playbook_code,
                                'name': metadata.name,
                                'description': metadata.description or '',
                                'tags': metadata.tags or []
                            })
                except Exception as e:
                    logger.debug(f"Could not load playbooks for welcome message: {e}")

                # Get active intents
                active_intents = []
                try:
                    from backend.app.models.mindscape import IntentStatus
                    intents = store.list_intents(
                        profile_id=profile_id,
                        status=IntentStatus.ACTIVE
                    )
                    active_intents = [{'title': i.title, 'description': i.description or ''} for i in intents[:5]]
                except Exception as e:
                    logger.debug(f"Could not load intents for welcome message: {e}")

                # Build LLM prompt for personalized welcome message
                system_prompt = f"""You are a helpful AI assistant welcoming a user to their new workspace "{workspace.title}".

Generate a warm, personalized welcome message that:
1. Welcomes the user to the workspace by name
2. Explains what this workspace is for (based on workspace title and description)
3. Mentions available capabilities/playbooks that might be useful
4. References any active intents/goals if they exist
5. Provides clear next steps and guidance
6. Is conversational, friendly, and encouraging
7. Uses the workspace's language/locale ({locale})

Keep it concise but informative (2-4 paragraphs)."""

                user_prompt = f"""Workspace Information:
- Title: {workspace.title}
- Description: {workspace.description or 'No description'}
- Mode: {workspace.mode or 'Not specified'}

Available Capabilities/Playbooks:
{chr(10).join([f"- {pb['name']} ({pb['playbook_code']}): {pb['description']}" for pb in available_playbooks[:10]]) if available_playbooks else "No specific playbooks configured yet"}

Active Goals/Intents:
{chr(10).join([f"- {intent['title']}: {intent['description']}" for intent in active_intents]) if active_intents else "No active intents yet - this is a fresh start!"}

Context:
{context if context else "This is a brand new workspace with no history yet."}

Generate a personalized welcome message for this workspace."""

                # Generate welcome message using LLM
                # Model must be configured by user in settings panel
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

                result = await generate_text(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=0.7,
                    max_tokens=500,
                    locale=locale,
                    workspace_id=workspace.id,
                    available_playbooks=available_playbooks
                )
                welcome_message = result.get('text', '') if isinstance(result, dict) else str(result)
                if not welcome_message or len(welcome_message.strip()) < 10:
                    # Fallback to i18n if LLM generation failed or returned empty
                    raise ValueError("LLM generated empty or invalid welcome message")

                logger.info(f"Generated LLM welcome message for workspace {workspace.id}")

            except Exception as e:
                logger.warning(f"Failed to generate LLM welcome message, falling back to i18n: {e}")
                welcome_message = i18n.t("workspace", "welcome.new_workspace", workspace_title=workspace.title)
        else:
            welcome_message = i18n.t("workspace", "welcome.returning_workspace", workspace_title=workspace.title)

        suggestions = [
            i18n.t("workspace", "suggestions.organize_tasks"),
            i18n.t("workspace", "suggestions.daily_planning"),
            i18n.t("workspace", "suggestions.view_progress")
        ]

        if workspace.default_playbook_id:
            try:
                from ...services.playbook_loader import PlaybookLoader
                loader = PlaybookLoader()
                playbook = loader.get_playbook_by_code(workspace.default_playbook_id)
                if playbook:
                    suggestions.insert(0, i18n.t("workspace", "suggestions.execute_playbook", playbook_name=playbook.metadata.name))
            except Exception:
                suggestions.insert(0, i18n.t("workspace", "suggestions.execute_playbook", playbook_name=workspace.default_playbook_id))

        return welcome_message, suggestions
    except Exception as e:
        logger.warning(f"Failed to generate personalized welcome message: {e}")
        i18n = get_i18n_service(default_locale=locale)
        return i18n.t("workspace", "welcome.fallback", workspace_title=workspace.title), [
            i18n.t("workspace", "suggestions.organize_tasks"),
            i18n.t("workspace", "suggestions.daily_planning")
        ]


# ============================================================================
# Workspace Management Endpoints (CRUD)
# ============================================================================

@router.get("", response_model=List[Workspace])
async def list_workspaces(
    owner_user_id: str = Query(..., description="Owner user ID"),
    primary_project_id: Optional[str] = Query(None, description="Filter by primary project ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of workspaces")
):
    """
    List workspaces for a user

    Returns list of workspaces owned by the user, optionally filtered by project.
    """
    try:
        workspaces = store.list_workspaces(
            owner_user_id=owner_user_id,
            primary_project_id=primary_project_id,
            limit=limit
        )
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
        allowed_dirs = _get_allowed_directories()

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
                # Inline validation call to avoid omission
                if not _validate_path_in_allowed_directories(requested_path, allowed_dirs):
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
            # Critical security check, must execute after all path construction
            # Inline validation call to avoid omission
            if allowed_dirs and not _validate_path_in_allowed_directories(workspace_storage_path, allowed_dirs):
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
            default_base = await _get_default_storage_path(store)

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
        workspace = Workspace(
            id=str(uuid.uuid4()),
            title=request.title,
            description=request.description,
            owner_user_id=owner_user_id,
            primary_project_id=request.primary_project_id,
            default_playbook_id=request.default_playbook_id,
            default_locale=request.default_locale,
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

        # Auto-register background routine for state sync
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

        locale = created.locale if hasattr(created, 'locale') and created.locale else "en"
        welcome_message, suggestions = await _generate_welcome_message(created, owner_user_id, store, locale=locale)
        if welcome_message:
            welcome_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.ASSISTANT,
                channel="local_workspace",
                profile_id=owner_user_id,
                project_id=request.primary_project_id,
                workspace_id=created.id,
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


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str = PathParam(..., description="Workspace ID")
):
    """
    Get workspace by ID

    Returns workspace details including configuration, metadata, and associated intent.
    """
    try:
        workspace = store.get_workspace(workspace_id)
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
        return workspace_dict
    except HTTPException:
        raise
    except Exception as e:
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
        if request.primary_project_id is not None:
            workspace.primary_project_id = request.primary_project_id
        if request.default_playbook_id is not None:
            workspace.default_playbook_id = request.default_playbook_id
        if request.default_locale is not None:
            workspace.default_locale = request.default_locale
        request_dict = request.dict(exclude_unset=False)
        if 'mode' in request_dict:
            workspace.mode = request.mode

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
                allowed_dirs = _get_allowed_directories()
                if allowed_dirs and not _validate_path_in_allowed_directories(new_path, allowed_dirs):
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
                    allowed_dirs = _get_allowed_directories()
                    if allowed_dirs and not _validate_path_in_allowed_directories(new_path, allowed_dirs):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Playbook storage path {new_path} for {playbook_code} is not within allowed directories. This may indicate a security issue."
                        )
            workspace.playbook_storage_config = request.playbook_storage_config
            logger.info(f"Updated playbook_storage_config for workspace {workspace_id}")

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
# Mount Sub-Routers
# ============================================================================
# Sub-routers are loaded via pack registry
# See backend/packs/workspace-pack.yaml and backend/features/workspace/

