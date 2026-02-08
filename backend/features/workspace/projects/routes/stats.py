"""
Projects API routes for Workspace-based projects - Stats and Analytics
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict
from pathlib import Path as FilePath

from fastapi import APIRouter, HTTPException, Path, Depends
from pydantic import BaseModel

from backend.app.routes.workspace_dependencies import get_workspace, get_store
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_manager import ProjectManager
from backend.app.models.workspace import Workspace, ExecutionSession
from backend.app.models.project import Project

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/{workspace_id}/projects/{project_id}/execution-tree",
    response_model=Dict[str, Any],
)
async def get_project_execution_tree(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
):
    """
    Get execution tree for a project, grouped by playbook

    Returns executions grouped by playbook_code with statistics.

    Args:
        workspace_id: Workspace ID
        project_id: Project ID

    Returns:
        Execution tree data with playbookGroups
    """
    try:
        from backend.app.services.stores.tasks_store import TasksStore

        project_manager = ProjectManager(store)
        project = await project_manager.get_project(
            project_id, workspace_id=workspace_id
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        tasks_store = TasksStore(db_path=store.db_path)

        # Get all execution tasks for this workspace
        all_execution_tasks = tasks_store.list_executions_by_workspace(
            workspace_id=workspace_id, limit=500
        )

        # Filter executions by project_id (with fallbacks to avoid losing data when context is missing)
        project_executions = []
        for task in all_execution_tasks:
            execution_context = task.execution_context or {}
            exec_project_id = execution_context.get("project_id") or (
                task.params or {}
            ).get("project_id")

            # If project_id is explicitly set and does not match, skip
            if exec_project_id and exec_project_id != project_id:
                continue

            # Fallback: if missing, assume this execution belongs to the requested project
            if not exec_project_id:
                exec_project_id = project_id
                execution_context["project_id"] = project_id

            # Ensure project name is present in context
            execution_context["project_name"] = (
                execution_context.get("project_name") or project.title
            )

            try:
                execution = ExecutionSession.from_task(task)
                execution_dict = (
                    execution.model_dump()
                    if hasattr(execution, "model_dump")
                    else execution
                )
                if isinstance(execution_dict, dict):
                    execution_dict["status"] = task.status.value
                    execution_dict["created_at"] = (
                        task.created_at.isoformat() if task.created_at else None
                    )
                    execution_dict["started_at"] = (
                        task.started_at.isoformat() if task.started_at else None
                    )
                    execution_dict["completed_at"] = (
                        task.completed_at.isoformat() if task.completed_at else None
                    )
                    execution_dict["project_id"] = exec_project_id
                    execution_dict["project_name"] = project.title

                    # Keep execution_context in the nested task as well, so frontend can read project_id/project_name
                    if isinstance(execution_dict.get("task"), dict):
                        task_ctx = execution_dict["task"].get("execution_context") or {}
                        task_ctx.setdefault("project_id", exec_project_id)
                        task_ctx.setdefault("project_name", project.title)
                        execution_dict["task"]["execution_context"] = task_ctx

                        # Optimization: Strip heavy result from nested task
                        if "result" in execution_dict["task"]:
                            execution_dict["task"]["result"] = None

                    # Critical Optimization: Strip heavy fields before returning to frontend
                    execution_dict["result"] = None
                    # We can keep execution_context as it's usually small, but result is huge (18MB+)

                project_executions.append(execution_dict)
            except Exception as e:
                logger.warning(
                    f"Failed to create ExecutionSession from task {task.id}: {e}"
                )

        # Group executions by playbook_code
        playbook_groups = defaultdict(
            lambda: {
                "playbookCode": "",
                "playbookName": "",
                "executions": [],
                "stats": {
                    "running": 0,
                    "paused": 0,
                    "queued": 0,
                    "completed": 0,
                    "failed": 0,
                },
            }
        )

        for exec_dict in project_executions:
            playbook_code = exec_dict.get("playbook_code") or "unknown"
            playbook_name = exec_dict.get("playbook_title") or playbook_code

            group = playbook_groups[playbook_code]
            group["playbookCode"] = playbook_code
            group["playbookName"] = playbook_name
            group["executions"].append(exec_dict)

            # Update stats
            status = exec_dict.get("status", "").lower()
            if status == "running":
                group["stats"]["running"] += 1
            elif status == "paused":
                group["stats"]["paused"] += 1
            elif status in ["queued", "pending"]:
                group["stats"]["queued"] += 1
            elif status in ["succeeded", "completed", "done"]:
                group["stats"]["completed"] += 1
            elif status in ["failed", "error"]:
                group["stats"]["failed"] += 1

        # Convert to list and sort executions within each group
        playbook_groups_list = []
        for playbook_code, group in playbook_groups.items():
            # Sort executions by created_at (earliest first)
            group["executions"].sort(
                key=lambda e: (
                    e.get("created_at") or e.get("started_at") or "1970-01-01"
                )
            )
            playbook_groups_list.append(group)

        # Sort groups by playbook_code
        playbook_groups_list.sort(key=lambda g: g["playbookCode"])

        return {
            "playbookGroups": playbook_groups_list,
            "projectId": project_id,
            "projectName": project.title,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project execution tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/projects/{project_id}/card", response_model=Dict[str, Any])
async def get_project_card(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
):
    """
    Get project card data with stats, progress, and recent events

    Returns comprehensive project card data including:
    - Project metadata (name, mind lens, status)
    - Statistics (running executions, pending confirmations, completed, artifacts)
    - Progress information
    - Recent events (playbook started, step completed, artifact created, confirmation needed)

    Args:
        workspace_id: Workspace ID
        project_id: Project ID

    Returns:
        Project card data
    """
    try:
        project_manager = ProjectManager(store)
        project = await project_manager.get_project(
            project_id, workspace_id=workspace_id
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Ensure flow exists, create if not (for existing projects that don't have flow yet)
        if project.flow_id:
            from backend.app.services.stores.playbook_flows_store import (
                PlaybookFlowsStore,
            )
            from backend.app.models.playbook_flow import PlaybookFlow
            from backend.app.services.project.project_detector import ProjectDetector

            flows_store = PlaybookFlowsStore(store.db_path)
            flow = flows_store.get_flow(project.flow_id)

            if not flow:
                logger.info(
                    f"Flow {project.flow_id} not found for project {project_id}, creating flow with LLM analysis"
                )
                # Use LLM to suggest playbook_sequence based on project info
                project_detector = ProjectDetector()

                # Build message for LLM analysis
                message = f"{project.title}"
                if project.type:
                    message += f" (type: {project.type})"

                # Check metadata for additional context
                if project.metadata and isinstance(project.metadata, dict):
                    primary_intent = project.metadata.get("primary_intent")
                    if primary_intent:
                        message += f"\n\nOriginal intent: {primary_intent}"

                # Get playbook_sequence suggestion from LLM
                try:
                    suggestion = await project_detector.detect(
                        message=message, conversation_context=[], workspace=workspace
                    )

                    if (
                        suggestion
                        and suggestion.mode == "project"
                        and suggestion.playbook_sequence
                    ):
                        raw_playbook_sequence = suggestion.playbook_sequence
                        logger.info(
                            f"LLM suggested {len(raw_playbook_sequence)} playbooks for project {project_id}"
                        )

                        # Validate playbook existence before creating flow (using unified validator)
                        from backend.app.services.project.playbook_validator import (
                            validate_playbook_sequence,
                        )

                        # Adjust path for increased nesting level
                        base_dir = FilePath(__file__).parent.parent.parent.parent.parent
                        playbook_sequence = validate_playbook_sequence(
                            raw_playbook_sequence, base_dir
                        )
                    else:
                        playbook_sequence = []
                        logger.warning(
                            f"LLM did not suggest playbooks for project {project_id}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to get LLM suggestion for project {project_id}: {e}"
                    )
                    playbook_sequence = []

                # Create flow with validated playbook_sequence (only existing playbooks)
                flow = PlaybookFlow(
                    id=project.flow_id,
                    name=(
                        f"{project.type.replace('_', ' ').title()} Flow"
                        if project.type
                        else "Flow"
                    ),
                    description=(
                        f"Flow for {project.type} projects"
                        if project.type
                        else "Default flow"
                    ),
                    flow_definition={
                        "nodes": [],
                        "edges": [],
                        "playbook_sequence": playbook_sequence,
                    },
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                flows_store.create_flow(flow)
                logger.info(
                    f"Created flow: {project.flow_id} with {len(playbook_sequence)} validated playbooks for project {project_id}"
                )

        # Get executions for this project using direct project_id query
        from backend.app.services.stores.tasks_store import TasksStore
        from backend.app.services.stores.events_store import EventsStore

        tasks_store = TasksStore(store.db_path)
        executions_store = store.playbook_executions
        events_store = EventsStore(store.db_path)

        # Direct query by project_id (optimized path)
        project_execution_tasks = tasks_store.list_executions_by_project(
            workspace_id=workspace_id, project_id=project_id, limit=500
        )
        logger.info(
            f"[ProjectCard] Found {len(project_execution_tasks)} execution tasks for project {project_id} via direct query"
        )

        # Fallback: If no tasks found via project_id, try matching by playbook_code and project flow
        # This handles cases where old tasks don't have project_id set
        if not project_execution_tasks and project.flow_id:
            try:
                from backend.app.services.stores.playbook_flows_store import (
                    PlaybookFlowsStore,
                )

                flows_store = PlaybookFlowsStore(store.db_path)
                flow = flows_store.get_flow(project.flow_id)
                if flow:
                    flow_def = (
                        flow.flow_definition
                        if isinstance(flow.flow_definition, dict)
                        else {}
                    )
                    playbook_sequence = flow_def.get("playbook_sequence", [])
                    if playbook_sequence:
                        # Get all execution tasks and filter by playbook_code
                        all_execution_tasks = tasks_store.list_executions_by_workspace(
                            workspace_id=workspace_id, limit=500
                        )
                        for task in all_execution_tasks:
                            execution_context = task.execution_context or {}
                            playbook_code = (
                                execution_context.get("playbook_code") or task.pack_id
                            )
                            if playbook_code in playbook_sequence:
                                project_execution_tasks.append(task)
                                # Update task with project_id for future queries
                                if not task.project_id:
                                    # Note: We used to update the task here (write-on-read), but that causes
                                    # synchronous DB writes which block the event loop.
                                    # We now only update the in-memory object for display.
                                    pass

                        logger.info(
                            f"[ProjectCard] Found {len(project_execution_tasks)} execution tasks via playbook_code matching (fallback)"
                        )
            except Exception as e:
                logger.debug(f"Fallback matching failed: {e}")

        # Get events for this project to find execution IDs (for fallback)
        project_events = events_store.get_events_by_project(
            project_id=project_id, limit=200
        )

        # [REMOVED] Sync Full Table Scan (Fallback)
        # Optimized for performance: relying only on tasks_store.
        all_workspace_events = []

        # Convert execution tasks to execution objects
        project_executions = []
        logger.info(
            f"[ProjectCard] Found {len(project_execution_tasks)} execution tasks for project {project_id}"
        )
        for task in project_execution_tasks:
            try:
                # Create a simple execution dict from task (don't use ExecutionSession which may not exist)
                execution_context = task.execution_context or {}
                execution_dict = {
                    "id": task.id,
                    "execution_id": task.id,
                    "status": task.status.value,
                    "playbook_code": execution_context.get("playbook_code")
                    or task.pack_id,
                    "created_at": (
                        task.created_at.isoformat() if task.created_at else None
                    ),
                    "started_at": (
                        task.started_at.isoformat() if task.started_at else None
                    ),
                    "completed_at": (
                        task.completed_at.isoformat() if task.completed_at else None
                    ),
                    "project_id": project_id,
                    "project_name": project.title,
                    "task": {"id": task.id, "execution_context": execution_context},
                }
                project_executions.append(execution_dict)
                logger.info(
                    f"[ProjectCard] Added execution {task.id[:8]} with status {task.status.value}, playbook_code={execution_dict['playbook_code']}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to create execution dict from task {task.id}: {e}",
                    exc_info=True,
                )

        # Fallback: Extract unique execution IDs from events (if no tasks found)
        if not project_executions:
            execution_ids = set()
            for event in project_events:
                if event.payload and isinstance(event.payload, dict):
                    exec_id = event.payload.get("execution_id")
                    if exec_id:
                        execution_ids.add(exec_id)
                if event.entity_ids:
                    for entity_id in event.entity_ids:
                        if (
                            entity_id
                            and len(entity_id) == 36
                            and entity_id.count("-") == 4
                        ):
                            execution_ids.add(entity_id)

            # Also check workspace events for execution IDs
            for event in all_workspace_events:
                if event.payload and isinstance(event.payload, dict):
                    exec_id = event.payload.get("execution_id")
                    playbook_code = event.payload.get("playbook_code")
                    if exec_id and playbook_code:
                        # Check if this playbook is part of the project's flow
                        if project.flow_id:
                            from backend.app.services.stores.playbook_flows_store import (
                                PlaybookFlowsStore,
                            )

                            flows_store = PlaybookFlowsStore(store.db_path)
                            flow = flows_store.get_flow(project.flow_id)
                            if flow:
                                flow_def = (
                                    flow.flow_definition
                                    if isinstance(flow.flow_definition, dict)
                                    else {}
                                )
                                playbook_sequence = flow_def.get(
                                    "playbook_sequence", []
                                )
                                if playbook_code in playbook_sequence:
                                    execution_ids.add(exec_id)
                        else:
                            execution_ids.add(exec_id)

            # Get executions by IDs
            for exec_id in execution_ids:
                exec_obj = executions_store.get_execution(exec_id)
                if exec_obj:
                    project_executions.append(exec_obj)

        if not project_executions:
            # Count executions from workspace events
            execution_status_map = {}
            for event in all_workspace_events:
                if event.payload and isinstance(event.payload, dict):
                    exec_id = event.payload.get("execution_id")
                    playbook_code = event.payload.get("playbook_code")
                    if exec_id and playbook_code:
                        # Include all executions from workspace events
                        # We'll filter by playbook_code matching project flow if flow exists
                        should_include = True
                        if project.flow_id:
                            try:
                                from backend.app.services.stores.playbook_flows_store import (
                                    PlaybookFlowsStore,
                                )

                                flows_store = PlaybookFlowsStore(store.db_path)
                                flow = flows_store.get_flow(project.flow_id)
                                if flow:
                                    flow_def = (
                                        flow.flow_definition
                                        if isinstance(flow.flow_definition, dict)
                                        else {}
                                    )
                                    playbook_sequence = flow_def.get(
                                        "playbook_sequence", []
                                    )
                                    if playbook_sequence:
                                        should_include = (
                                            playbook_code in playbook_sequence
                                        )
                            except:
                                # If flow lookup fails, include all
                                should_include = True

                        if should_include and exec_id not in execution_status_map:
                            execution_status_map[exec_id] = {
                                "playbook_code": playbook_code,
                                "status": "running",  # Default to running if not in DB
                            }

            # Create mock execution objects for stats calculation
            from types import SimpleNamespace

            for exec_id, exec_data in execution_status_map.items():
                mock_exec = SimpleNamespace(
                    id=exec_id,
                    playbook_code=exec_data["playbook_code"],
                    status=exec_data["status"],
                    phase=None,
                )
                project_executions.append(mock_exec)

        # Calculate stats
        # Handle both dict and object formats
        def get_status(exec_obj):
            if isinstance(exec_obj, dict):
                return exec_obj.get("status", "").lower()
            return (exec_obj.status if hasattr(exec_obj, "status") else "").lower()

        logger.info(
            f"[ProjectCard] Calculating stats from {len(project_executions)} executions"
        )
        for exec_obj in project_executions:
            status = get_status(exec_obj)
            logger.debug(
                f"[ProjectCard] Execution {exec_obj.get('id', 'unknown')[:8] if isinstance(exec_obj, dict) else 'unknown'}: status={status}"
            )

        running_executions = [
            e for e in project_executions if get_status(e) == "running"
        ]
        completed_executions = [
            e
            for e in project_executions
            if get_status(e) in ["completed", "succeeded", "done"]
        ]

        logger.info(
            f"[ProjectCard] Stats: running={len(running_executions)}, completed={len(completed_executions)}, total={len(project_executions)}"
        )

        # Get pending confirmations (executions waiting for confirmation)
        pending_confirmations = []
        for exec_obj in project_executions:
            status = get_status(exec_obj)
            phase = None
            if isinstance(exec_obj, dict):
                phase = exec_obj.get("phase")
            elif hasattr(exec_obj, "phase"):
                phase = exec_obj.phase
            if status == "running" and phase and "waiting" in str(phase).lower():
                pending_confirmations.append(exec_obj)

        # Get artifacts count
        from backend.app.services.project.artifact_registry_service import (
            ArtifactRegistryService,
        )

        artifact_registry = ArtifactRegistryService(store)
        artifacts = await artifact_registry.list_artifacts(project_id=project_id)

        # Get playbooks count and list (from flow or metadata)
        total_playbooks = 0
        playbook_list = []
        if project.flow_id:
            from backend.app.services.stores.playbook_flows_store import (
                PlaybookFlowsStore,
            )

            flows_store = PlaybookFlowsStore(store.db_path)
            flow = flows_store.get_flow(project.flow_id)
            if flow:
                # Get playbook_sequence from flow_definition
                flow_def = (
                    flow.flow_definition
                    if isinstance(flow.flow_definition, dict)
                    else {}
                )
                playbook_sequence = flow_def.get("playbook_sequence", [])

                if playbook_sequence:
                    # Get playbook details (playbook_sequence is already validated when flow was created)
                    from backend.app.services.playbook_loaders.file_loader import (
                        PlaybookFileLoader,
                    )

                    total_playbooks = len(playbook_sequence)
                    # Adjust Base Dir
                    base_dir = FilePath(__file__).parent.parent.parent.parent.parent

                    for playbook_code in playbook_sequence:
                        playbook_name = playbook_code.replace("_", " ").title()
                        playbook_description = ""

                        # Load playbook details from i18n markdown files
                        for locale in ["zh-TW", "en", "ja"]:
                            i18n_dir = (
                                base_dir / "backend" / "i18n" / "playbooks" / locale
                            )
                            md_file = i18n_dir / f"{playbook_code}.md"

                            if md_file.exists():
                                try:
                                    playbook = (
                                        PlaybookFileLoader.load_playbook_from_file(
                                            md_file
                                        )
                                    )
                                    if playbook and playbook.metadata:
                                        playbook_name = (
                                            playbook.metadata.name
                                            if playbook.metadata.name
                                            else playbook_name
                                        )
                                        if not playbook_description:
                                            playbook_description = (
                                                playbook.metadata.description
                                                if playbook.metadata.description
                                                else ""
                                            )
                                        # Found valid playbook, break
                                        break
                                except Exception as e:
                                    logger.debug(
                                        f"Failed to load playbook {playbook_code} from {locale} markdown: {e}"
                                    )

                        playbook_list.append(
                            {
                                "code": playbook_code,
                                "name": playbook_name,
                                "description": playbook_description,
                            }
                        )
                else:
                    logger.info(f"Flow {project.flow_id} has no playbook_sequence")
            else:
                logger.warning(
                    f"Flow {project.flow_id} not found for project {project_id}"
                )
        else:
            logger.warning(
                f"Project {project_id} has no flow_id, cannot determine playbooks"
            )

        # Calculate progress
        if total_playbooks > 0:
            # Extract playbook_code from executions (handle both dict and object formats)
            def get_playbook_code(exec_obj):
                if isinstance(exec_obj, dict):
                    return exec_obj.get("playbook_code") or exec_obj.get(
                        "task", {}
                    ).get("execution_context", {}).get("playbook_code")
                return (
                    exec_obj.playbook_code
                    if hasattr(exec_obj, "playbook_code")
                    else None
                )

            completed_playbooks = len(
                set(
                    [
                        get_playbook_code(e)
                        for e in completed_executions
                        if get_playbook_code(e)
                    ]
                )
            )
            # Cap progress at 100% if completed exceeds total (can happen if playbooks were added after execution)
            progress_current = (
                min(100, int((completed_playbooks / total_playbooks) * 100))
                if total_playbooks > 0
                else 0
            )
            progress_label = f"{completed_playbooks}/{total_playbooks} Playbooks 完成"
            logger.info(
                f"[ProjectCard] Progress: {completed_playbooks}/{total_playbooks} playbooks completed, {progress_current}%"
            )
        else:
            progress_current = 0
            progress_label = "尚未開始"

        # Get recent events for card display
        # Use the all_workspace_events we already fetched earlier
        recent_events_list = []

        # First try project events
        project_events_for_display = events_store.get_events_by_project(
            project_id=project_id, limit=10
        )
        recent_events_list.extend(project_events_for_display)

        # Always get workspace events that match our project executions
        # Use the all_workspace_events we already fetched earlier
        # [PERFORMANCE FIX] Second sync full table scan removed.
        # This logic (duplicate of the one removed earlier) caused severe event loop blocking.
        pass

        # Transform events to card format
        card_events = []
        # [PERFORMANCE] Instantiate Registry once outside the loop to avoid disk thrashing
        from backend.app.services.playbook_registry import PlaybookRegistry

        playbook_registry = PlaybookRegistry()

        for event in recent_events_list[:5]:
            event_type = None
            playbook_code = None
            playbook_name = None
            # ... (rest of loop logic)

            if event.payload and isinstance(event.payload, dict):
                # ...
                playbook_code = event.payload.get("playbook_code")
                # ...

                # Try to get playbook name
                if playbook_code:
                    try:
                        # Use cached registry lookup (lazy loaded)
                        playbook = await playbook_registry.get_playbook(
                            playbook_code, locale="zh-TW"
                        )
                        if playbook:
                            playbook_name = (
                                playbook.metadata.name
                                if hasattr(playbook.metadata, "name")
                                else playbook_code
                            )
                    except Exception:
                        playbook_name = playbook_code
            execution_id = None
            step_index = None
            step_name = None

            if event.payload and isinstance(event.payload, dict):
                execution_id = event.payload.get("execution_id")
                playbook_code = event.payload.get("playbook_code")

                # Determine event type from event_type
                event_type_str = (
                    event.event_type.value
                    if hasattr(event.event_type, "value")
                    else str(event.event_type)
                )
                if event_type_str == "EXECUTION_PLAN":
                    # Execution plan events indicate playbook started
                    event_type = "playbook_started"
                elif event_type_str == "MESSAGE":
                    # Check if it's assistant message (might indicate playbook started)
                    actor_str = (
                        event.actor.value
                        if hasattr(event.actor, "value")
                        else str(event.actor)
                    )
                    if actor_str == "ASSISTANT":
                        event_type = "playbook_started"
                elif (
                    "PLAYBOOK_STEP" in event_type_str
                    or "step" in event_type_str.lower()
                ):
                    event_type = "step_completed"
                elif (
                    "ARTIFACT" in event_type_str or "artifact" in event_type_str.lower()
                ):
                    event_type = "artifact_created"
                elif (
                    "CONFIRMATION" in event_type_str
                    or "confirmation" in event_type_str.lower()
                    or "waiting" in event_type_str.lower()
                ):
                    event_type = "confirmation_needed"

                # Try to get playbook name
                if playbook_code:
                    try:
                        # Use the registry instance created outside the loop
                        playbook = await playbook_registry.get_playbook(
                            playbook_code, locale="zh-TW"
                        )
                        if playbook:
                            playbook_name = (
                                playbook.metadata.name
                                if hasattr(playbook.metadata, "name")
                                else playbook_code
                            )
                    except Exception:
                        playbook_name = playbook_code

                step_index = event.payload.get("step_index")
                step_name = event.payload.get("step_name")

            # Only include events with valid type, and limit metadata size
            if event_type:
                # Limit metadata to essential fields only to avoid huge payloads
                limited_metadata = {}
                if event.payload and isinstance(event.payload, dict):
                    # Only include small, essential fields
                    for key in [
                        "execution_id",
                        "playbook_code",
                        "step_index",
                        "step_name",
                    ]:
                        if key in event.payload:
                            limited_metadata[key] = event.payload[key]

                card_events.append(
                    {
                        "id": event.id,
                        "type": event_type,
                        "playbookCode": playbook_code or "",
                        "playbookName": playbook_name or playbook_code or "Unknown",
                        "executionId": execution_id or "",
                        "stepIndex": step_index,
                        "stepName": step_name,
                        "timestamp": (
                            event.timestamp.isoformat()
                            if hasattr(event.timestamp, "isoformat")
                            else str(event.timestamp)
                        ),
                        "metadata": limited_metadata,
                    }
                )

        # Get mind lens info if available
        mind_lens_id = (
            project.metadata.get("mind_lens_id") if project.metadata else None
        )
        mind_lens_name = (
            project.metadata.get("mind_lens_name") if project.metadata else None
        )

        # Map project state to status
        status_map = {"open": "active", "closed": "completed", "archived": "archived"}
        status = status_map.get(project.state, "active")

        return {
            "projectId": project.id,
            "projectName": project.title,
            "storyThreadId": (
                project.metadata.get("story_thread_id") if project.metadata else None
            ),
            "mindLensId": mind_lens_id,
            "mindLensName": mind_lens_name,
            "status": status,
            "lastActivity": (
                project.updated_at.isoformat()
                if hasattr(project.updated_at, "isoformat")
                else str(project.updated_at)
            ),
            "stats": {
                "totalPlaybooks": total_playbooks,
                "runningExecutions": len(running_executions),
                "pendingConfirmations": len(pending_confirmations),
                "completedExecutions": len(completed_executions),
                "artifactCount": len(artifacts),
            },
            "progress": {"current": progress_current, "label": progress_label},
            "playbooks": playbook_list,
            "recentEvents": card_events,
        }
    except PermissionError as e:
        logger.error(f"Permission error getting project card: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project card: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
