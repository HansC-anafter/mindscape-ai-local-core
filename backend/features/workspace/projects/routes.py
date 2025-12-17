"""
Projects API routes for Workspace-based projects
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Path, Body, Depends, Query
from pydantic import BaseModel

from backend.app.routes.workspace_dependencies import get_workspace, get_store
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_manager import ProjectManager
from backend.app.services.project.flow_executor import FlowExecutor, FlowExecutionError
from backend.app.models.workspace import Workspace
from backend.app.models.project import Project, ProjectSuggestion

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-projects"])
logger = logging.getLogger(__name__)


class CreateProjectRequest(BaseModel):
    """Request model for creating a project"""
    suggestion: Optional[ProjectSuggestion] = None
    project_type: Optional[str] = None
    title: Optional[str] = None
    flow_id: Optional[str] = None
    initiator_user_id: Optional[str] = None
    human_owner_user_id: Optional[str] = None
    ai_pm_id: Optional[str] = None


@router.get("/{workspace_id}/projects")
async def list_projects(
    workspace_id: str = Path(..., description="Workspace ID"),
    state: Optional[str] = None,
    project_type: Optional[str] = Query(None, description="Filter by project type"),
    limit: int = 100,
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    List projects in workspace with optional filters

    Args:
        workspace_id: Workspace ID
        state: Optional state filter (open, closed, archived)
        project_type: Optional project type filter
        limit: Maximum number of projects to return

    Returns:
        List of projects with grouping by type
    """
    try:
        project_manager = ProjectManager(store)
        projects = await project_manager.list_projects(
            workspace_id=workspace_id,
            state=state,
            project_type=project_type,
            limit=limit
        )

        # Group projects by type for categorization
        projects_by_type: Dict[str, List[Dict[str, Any]]] = {}
        for project in projects:
            project_type_key = project.type or "other"
            if project_type_key not in projects_by_type:
                projects_by_type[project_type_key] = []
            projects_by_type[project_type_key].append(project.model_dump(mode='json'))

        # Calculate type counts
        type_counts = {k: len(v) for k, v in projects_by_type.items()}

        return {
            "projects": [p.model_dump(mode='json') for p in projects],
            "projects_by_type": projects_by_type,
            "type_counts": type_counts
        }
    except Exception as e:
        logger.error(f"Failed to list projects: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/projects/{project_id}")
async def get_project(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Get project details

    Args:
        workspace_id: Workspace ID
        project_id: Project ID

    Returns:
        Project details
    """
    try:
        project_manager = ProjectManager(store)
        project = await project_manager.get_project(project_id, workspace_id=workspace_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project.model_dump(mode='json')
    except PermissionError as e:
        logger.error(f"Permission error getting project: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/projects")
async def create_project(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: CreateProjectRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Create new project

    Args:
        workspace_id: Workspace ID
        request: Project creation request (can use suggestion or direct fields)

    Returns:
        Created project
    """
    try:
        project_manager = ProjectManager(store)

        # If suggestion is provided, use it
        if request.suggestion:
            suggestion = request.suggestion
            if suggestion.mode != 'project':
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid suggestion mode: {suggestion.mode}. Expected 'project'"
                )

            if not suggestion.project_type or not suggestion.project_title or not suggestion.flow_id:
                raise HTTPException(
                    status_code=400,
                    detail="Suggestion must include project_type, project_title, and flow_id"
                )

            # Use default initiator_user_id from identity port
            from backend.app.routes.workspace_dependencies import get_identity_port_or_default
            identity_port = get_identity_port_or_default()
            context = await identity_port.get_current_context(workspace_id=workspace_id)
            initiator_user_id = context.actor_id

            project = await project_manager.create_project(
                project_type=suggestion.project_type,
                title=suggestion.project_title,
                workspace_id=workspace_id,
                flow_id=suggestion.flow_id,
                initiator_user_id=initiator_user_id,
                metadata={
                    'initial_spec_md': suggestion.initial_spec_md,
                    'confidence': suggestion.confidence
                } if suggestion.initial_spec_md else {}
            )
        else:
            # Direct creation
            if not request.project_type or not request.title or not request.flow_id:
                raise HTTPException(
                    status_code=400,
                    detail="project_type, title, and flow_id are required"
                )

            from backend.app.routes.workspace_dependencies import get_identity_port_or_default
            identity_port = get_identity_port_or_default()
            context = await identity_port.get_current_context(workspace_id=workspace_id)
            initiator_user_id = request.initiator_user_id or context.actor_id

            project = await project_manager.create_project(
                project_type=request.project_type,
                title=request.title,
                workspace_id=workspace_id,
                flow_id=request.flow_id,
                initiator_user_id=initiator_user_id,
                human_owner_user_id=request.human_owner_user_id,
                ai_pm_id=request.ai_pm_id
            )

        return {"project": project.model_dump(mode='json')}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class ExecuteFlowRequest(BaseModel):
    """Request model for executing a project flow"""
    resume_from: Optional[str] = None
    preserve_artifacts: bool = True
    max_retries: int = 3


@router.post("/{workspace_id}/projects/{project_id}/execute-flow")
async def execute_project_flow(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    request: ExecuteFlowRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Execute PlaybookFlow for a project

    Starts or resumes flow execution for the specified project.
    Supports partial retry from a specific node and artifact preservation.

    Args:
        workspace_id: Workspace ID
        project_id: Project ID
        request: Flow execution request with optional resume_from, preserve_artifacts, max_retries

    Returns:
        Flow execution result with node outcomes
    """
    try:
        project_manager = ProjectManager(store)
        project = await project_manager.get_project(project_id, workspace_id=workspace_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        from backend.app.routes.workspace_dependencies import get_identity_port_or_default
        identity_port = get_identity_port_or_default()
        context = await identity_port.get_current_context(workspace_id=workspace_id)
        profile_id = context.actor_id

        flow_executor = FlowExecutor(store)
        result = await flow_executor.execute_flow(
            project_id=project_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            resume_from=request.resume_from,
            preserve_artifacts=request.preserve_artifacts,
            max_retries=request.max_retries
        )

        return {
            "status": "executing",
            "execution_result": result
        }

    except FlowExecutionError as e:
        logger.error(f"Flow execution error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission error executing flow: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute flow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/projects/{project_id}/flow-status")
async def get_flow_status(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Get flow execution status for a project

    Returns current flow execution status including completed nodes,
    failed nodes, and checkpoint information.

    Args:
        workspace_id: Workspace ID
        project_id: Project ID

    Returns:
        Flow execution status
    """
    try:
        project_manager = ProjectManager(store)
        project = await project_manager.get_project(project_id, workspace_id=workspace_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        from backend.app.services.project.artifact_registry_service import ArtifactRegistryService
        artifact_registry = ArtifactRegistryService(store)
        artifacts = await artifact_registry.list_artifacts(project_id=project_id)

        checkpoint = project.metadata.get("last_checkpoint")

        return {
            "project_id": project_id,
            "flow_id": project.flow_id,
            "status": "ready",
            "artifacts_count": len(artifacts),
            "checkpoint": checkpoint,
            "artifacts": [
                {
                    "artifact_id": a.artifact_id,
                    "type": a.type,
                    "created_by": a.created_by,
                    "created_at": a.created_at.isoformat()
                }
                for a in artifacts[:10]
            ]
        }

    except PermissionError as e:
        logger.error(f"Permission error getting flow status: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get flow status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/projects/{project_id}/execution-tree")
async def get_project_execution_tree(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
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
        from backend.app.models.workspace import ExecutionSession
        from collections import defaultdict

        project_manager = ProjectManager(store)
        project = await project_manager.get_project(project_id, workspace_id=workspace_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        tasks_store = TasksStore(db_path=store.db_path)

        # Get all execution tasks for this workspace
        all_execution_tasks = tasks_store.list_executions_by_workspace(workspace_id=workspace_id, limit=500)

        # Filter executions by project_id (with fallbacks to avoid losing data when context is missing)
        project_executions = []
        for task in all_execution_tasks:
            execution_context = task.execution_context or {}
            exec_project_id = (
                execution_context.get("project_id")
                or (task.params or {}).get("project_id")
            )

            # If project_id is explicitly set and does not match, skip
            if exec_project_id and exec_project_id != project_id:
                continue

            # Fallback: if missing, assume this execution belongs to the requested project
            if not exec_project_id:
                exec_project_id = project_id
                execution_context["project_id"] = project_id

            # Ensure project name is present in context
            execution_context["project_name"] = execution_context.get("project_name") or project.title

            try:
                execution = ExecutionSession.from_task(task)
                execution_dict = execution.model_dump() if hasattr(execution, 'model_dump') else execution
                if isinstance(execution_dict, dict):
                    execution_dict["status"] = task.status.value
                    execution_dict["created_at"] = task.created_at.isoformat() if task.created_at else None
                    execution_dict["started_at"] = task.started_at.isoformat() if task.started_at else None
                    execution_dict["completed_at"] = task.completed_at.isoformat() if task.completed_at else None
                    execution_dict["project_id"] = exec_project_id
                    execution_dict["project_name"] = project.title

                    # Keep execution_context in the nested task as well, so frontend can read project_id/project_name
                    if isinstance(execution_dict.get("task"), dict):
                        task_ctx = execution_dict["task"].get("execution_context") or {}
                        task_ctx.setdefault("project_id", exec_project_id)
                        task_ctx.setdefault("project_name", project.title)
                        execution_dict["task"]["execution_context"] = task_ctx
                project_executions.append(execution_dict)
            except Exception as e:
                logger.warning(f"Failed to create ExecutionSession from task {task.id}: {e}")

        # Group executions by playbook_code
        playbook_groups = defaultdict(lambda: {
            "playbookCode": "",
            "playbookName": "",
            "executions": [],
            "stats": {
                "running": 0,
                "paused": 0,
                "queued": 0,
                "completed": 0,
                "failed": 0
            }
        })

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
            group["executions"].sort(key=lambda e: (
                e.get("created_at") or e.get("started_at") or "1970-01-01"
            ))
            playbook_groups_list.append(group)

        # Sort groups by playbook_code
        playbook_groups_list.sort(key=lambda g: g["playbookCode"])

        return {
            "playbookGroups": playbook_groups_list,
            "projectId": project_id,
            "projectName": project.title
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project execution tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/projects/{project_id}/card")
async def get_project_card(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
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
        project = await project_manager.get_project(project_id, workspace_id=workspace_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Ensure flow exists, create if not (for existing projects that don't have flow yet)
        if project.flow_id:
            from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore
            from backend.app.models.playbook_flow import PlaybookFlow
            from backend.app.services.project.project_detector import ProjectDetector
            flows_store = PlaybookFlowsStore(store.db_path)
            flow = flows_store.get_flow(project.flow_id)

            if not flow:
                logger.info(f"Flow {project.flow_id} not found for project {project_id}, creating flow with LLM analysis")
                # Use LLM to suggest playbook_sequence based on project info
                project_detector = ProjectDetector()

                # Build message for LLM analysis
                message = f"{project.title}"
                if project.type:
                    message += f" (type: {project.type})"

                # Check metadata for additional context
                if project.metadata and isinstance(project.metadata, dict):
                    primary_intent = project.metadata.get('primary_intent')
                    if primary_intent:
                        message += f"\n\nOriginal intent: {primary_intent}"

                # Get playbook_sequence suggestion from LLM
                try:
                    suggestion = await project_detector.detect(
                        message=message,
                        conversation_context=[],
                        workspace=workspace
                    )

                    if suggestion and suggestion.mode == "project" and suggestion.playbook_sequence:
                        raw_playbook_sequence = suggestion.playbook_sequence
                        logger.info(f"LLM suggested {len(raw_playbook_sequence)} playbooks for project {project_id}")

                        # Validate playbook existence before creating flow (using unified validator)
                        from backend.app.services.project.playbook_validator import validate_playbook_sequence
                        from pathlib import Path

                        base_dir = Path(__file__).parent.parent.parent.parent
                        playbook_sequence = validate_playbook_sequence(raw_playbook_sequence, base_dir)
                    else:
                        playbook_sequence = []
                        logger.warning(f"LLM did not suggest playbooks for project {project_id}")
                except Exception as e:
                    logger.warning(f"Failed to get LLM suggestion for project {project_id}: {e}")
                    playbook_sequence = []

                # Create flow with validated playbook_sequence (only existing playbooks)
                flow = PlaybookFlow(
                    id=project.flow_id,
                    name=f"{project.type.replace('_', ' ').title()} Flow" if project.type else "Flow",
                    description=f"Flow for {project.type} projects" if project.type else "Default flow",
                    flow_definition={
                        "nodes": [],
                        "edges": [],
                        "playbook_sequence": playbook_sequence
                    },
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                flows_store.create_flow(flow)
                logger.info(f"Created flow: {project.flow_id} with {len(playbook_sequence)} validated playbooks for project {project_id}")

        # Get executions for this project using direct project_id query
        from backend.app.services.stores.tasks_store import TasksStore
        from backend.app.services.stores.playbook_executions_store import PlaybookExecutionsStore
        from backend.app.services.stores.events_store import EventsStore
        tasks_store = TasksStore(store.db_path)
        executions_store = PlaybookExecutionsStore(store.db_path)
        events_store = EventsStore(store.db_path)

        # Direct query by project_id (optimized path)
        project_execution_tasks = tasks_store.list_executions_by_project(
            workspace_id=workspace_id,
            project_id=project_id,
            limit=500
        )
        logger.info(f"[ProjectCard] Found {len(project_execution_tasks)} execution tasks for project {project_id} via direct query")

        # Fallback: If no tasks found via project_id, try matching by playbook_code and project flow
        # This handles cases where old tasks don't have project_id set
        if not project_execution_tasks and project.flow_id:
            try:
                from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore
                flows_store = PlaybookFlowsStore(store.db_path)
                flow = flows_store.get_flow(project.flow_id)
                if flow:
                    flow_def = flow.flow_definition if isinstance(flow.flow_definition, dict) else {}
                    playbook_sequence = flow_def.get('playbook_sequence', [])
                    if playbook_sequence:
                        # Get all execution tasks and filter by playbook_code
                        all_execution_tasks = tasks_store.list_executions_by_workspace(workspace_id=workspace_id, limit=500)
                        for task in all_execution_tasks:
                            execution_context = task.execution_context or {}
                            playbook_code = execution_context.get("playbook_code") or task.pack_id
                            if playbook_code in playbook_sequence:
                                project_execution_tasks.append(task)
                                # Update task with project_id for future queries
                                if not task.project_id:
                                    try:
                                        tasks_store.update_task(task.id, project_id=project_id)
                                        logger.info(f"[ProjectCard] Updated task {task.id[:8]} with project_id {project_id}")
                                    except Exception as e:
                                        logger.debug(f"Failed to update task project_id: {e}")
                        logger.info(f"[ProjectCard] Found {len(project_execution_tasks)} execution tasks via playbook_code matching (fallback)")
            except Exception as e:
                logger.debug(f"Fallback matching failed: {e}")

        # Get events for this project to find execution IDs (for fallback)
        project_events = events_store.get_events_by_project(
            project_id=project_id,
            limit=200
        )

        # Also get all workspace events to find executions that might not have project_id set
        # This handles cases where events have execution_id but project_id is None
        # Query database directly to get workspace events
        import sqlite3
        import json
        from types import SimpleNamespace

        all_workspace_events = []
        try:
            conn = sqlite3.connect(store.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT payload, entity_ids
                FROM mind_events
                WHERE workspace_id = ?
                AND payload LIKE '%execution_id%'
                ORDER BY timestamp DESC
                LIMIT 500
            ''', (workspace_id,))
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                payload_str = row[0] if row[0] else '{}'
                entity_ids_str = row[1] if row[1] else '[]'
                payload = json.loads(payload_str) if payload_str else {}
                entity_ids = json.loads(entity_ids_str) if entity_ids_str else []
                if payload.get('execution_id'):
                    event = SimpleNamespace(
                        payload=payload,
                        entity_ids=entity_ids
                    )
                    all_workspace_events.append(event)
        except Exception as e:
            logger.warning(f"Failed to get workspace events: {e}")
            all_workspace_events = []

        # Convert execution tasks to execution objects
        project_executions = []
        logger.info(f"[ProjectCard] Found {len(project_execution_tasks)} execution tasks for project {project_id}")
        for task in project_execution_tasks:
            try:
                # Create a simple execution dict from task (don't use ExecutionSession which may not exist)
                execution_context = task.execution_context or {}
                execution_dict = {
                    "id": task.id,
                    "execution_id": task.id,
                    "status": task.status.value,
                    "playbook_code": execution_context.get("playbook_code") or task.pack_id,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "started_at": task.started_at.isoformat() if task.started_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    "project_id": project_id,
                    "project_name": project.title,
                    "task": {
                        "id": task.id,
                        "execution_context": execution_context
                    }
                }
                project_executions.append(execution_dict)
                logger.info(f"[ProjectCard] Added execution {task.id[:8]} with status {task.status.value}, playbook_code={execution_dict['playbook_code']}")
            except Exception as e:
                logger.warning(f"Failed to create execution dict from task {task.id}: {e}", exc_info=True)

        # Fallback: Extract unique execution IDs from events (if no tasks found)
        if not project_executions:
            execution_ids = set()
            for event in project_events:
                if event.payload and isinstance(event.payload, dict):
                    exec_id = event.payload.get('execution_id')
                    if exec_id:
                        execution_ids.add(exec_id)
                if event.entity_ids:
                    for entity_id in event.entity_ids:
                        if entity_id and len(entity_id) == 36 and entity_id.count('-') == 4:
                            execution_ids.add(entity_id)

            # Also check workspace events for execution IDs
            for event in all_workspace_events:
                if event.payload and isinstance(event.payload, dict):
                    exec_id = event.payload.get('execution_id')
                    playbook_code = event.payload.get('playbook_code')
                    if exec_id and playbook_code:
                        # Check if this playbook is part of the project's flow
                        if project.flow_id:
                            from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore
                            flows_store = PlaybookFlowsStore(store.db_path)
                            flow = flows_store.get_flow(project.flow_id)
                            if flow:
                                flow_def = flow.flow_definition if isinstance(flow.flow_definition, dict) else {}
                                playbook_sequence = flow_def.get('playbook_sequence', [])
                                if playbook_code in playbook_sequence:
                                    execution_ids.add(exec_id)
                        else:
                            execution_ids.add(exec_id)

            # Get executions by IDs
            for exec_id in execution_ids:
                exec_obj = executions_store.get_execution(exec_id)
                if exec_obj:
                    project_executions.append(exec_obj)

        # Fallback: Get all executions for workspace from events
        # Since executions don't exist in DB, we'll use events to infer stats
        if not project_executions:
            # Count executions from workspace events
            execution_status_map = {}
            for event in all_workspace_events:
                if event.payload and isinstance(event.payload, dict):
                    exec_id = event.payload.get('execution_id')
                    playbook_code = event.payload.get('playbook_code')
                    if exec_id and playbook_code:
                        # Include all executions from workspace events
                        # We'll filter by playbook_code matching project flow if flow exists
                        should_include = True
                        if project.flow_id:
                            try:
                                from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore
                                flows_store = PlaybookFlowsStore(store.db_path)
                                flow = flows_store.get_flow(project.flow_id)
                                if flow:
                                    flow_def = flow.flow_definition if isinstance(flow.flow_definition, dict) else {}
                                    playbook_sequence = flow_def.get('playbook_sequence', [])
                                    if playbook_sequence:
                                        should_include = playbook_code in playbook_sequence
                            except:
                                # If flow lookup fails, include all
                                should_include = True

                        if should_include and exec_id not in execution_status_map:
                            execution_status_map[exec_id] = {
                                'playbook_code': playbook_code,
                                'status': 'running'  # Default to running if not in DB
                            }

            # Create mock execution objects for stats calculation
            from types import SimpleNamespace
            for exec_id, exec_data in execution_status_map.items():
                mock_exec = SimpleNamespace(
                    id=exec_id,
                    playbook_code=exec_data['playbook_code'],
                    status=exec_data['status'],
                    phase=None
                )
                project_executions.append(mock_exec)

        # Calculate stats
        # Handle both dict and object formats
        def get_status(exec_obj):
            if isinstance(exec_obj, dict):
                return exec_obj.get('status', '').lower()
            return (exec_obj.status if hasattr(exec_obj, 'status') else '').lower()

        logger.info(f"[ProjectCard] Calculating stats from {len(project_executions)} executions")
        for exec_obj in project_executions:
            status = get_status(exec_obj)
            logger.debug(f"[ProjectCard] Execution {exec_obj.get('id', 'unknown')[:8] if isinstance(exec_obj, dict) else 'unknown'}: status={status}")

        running_executions = [e for e in project_executions if get_status(e) == 'running']
        completed_executions = [e for e in project_executions if get_status(e) in ['completed', 'succeeded', 'done']]

        logger.info(f"[ProjectCard] Stats: running={len(running_executions)}, completed={len(completed_executions)}, total={len(project_executions)}")

        # Get pending confirmations (executions waiting for confirmation)
        pending_confirmations = []
        for exec_obj in project_executions:
            status = get_status(exec_obj)
            phase = None
            if isinstance(exec_obj, dict):
                phase = exec_obj.get('phase')
            elif hasattr(exec_obj, 'phase'):
                phase = exec_obj.phase
            if status == 'running' and phase and 'waiting' in str(phase).lower():
                pending_confirmations.append(exec_obj)

        # Get artifacts count
        from backend.app.services.project.artifact_registry_service import ArtifactRegistryService
        artifact_registry = ArtifactRegistryService(store)
        artifacts = await artifact_registry.list_artifacts(project_id=project_id)

        # Get playbooks count and list (from flow or metadata)
        total_playbooks = 0
        playbook_list = []
        if project.flow_id:
            from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore
            flows_store = PlaybookFlowsStore(store.db_path)
            flow = flows_store.get_flow(project.flow_id)
            if flow:
                # Get playbook_sequence from flow_definition
                flow_def = flow.flow_definition if isinstance(flow.flow_definition, dict) else {}
                playbook_sequence = flow_def.get('playbook_sequence', [])

                if playbook_sequence:
                    # Get playbook details (playbook_sequence is already validated when flow was created)
                    from backend.app.services.playbook_loaders.file_loader import PlaybookFileLoader
                    from pathlib import Path

                    total_playbooks = len(playbook_sequence)
                    base_dir = Path(__file__).parent.parent.parent.parent

                    for playbook_code in playbook_sequence:
                        playbook_name = playbook_code.replace('_', ' ').title()
                        playbook_description = ""

                        # Load playbook details from i18n markdown files
                        for locale in ['zh-TW', 'en', 'ja']:
                            i18n_dir = base_dir / "backend" / "i18n" / "playbooks" / locale
                            md_file = i18n_dir / f"{playbook_code}.md"

                            if md_file.exists():
                                try:
                                    playbook = PlaybookFileLoader.load_playbook_from_file(md_file)
                                    if playbook and playbook.metadata:
                                        playbook_name = playbook.metadata.name if playbook.metadata.name else playbook_name
                                        if not playbook_description:
                                            playbook_description = playbook.metadata.description if playbook.metadata.description else ""
                                        # Found valid playbook, break
                                        break
                                except Exception as e:
                                    logger.debug(f"Failed to load playbook {playbook_code} from {locale} markdown: {e}")

                        playbook_list.append({
                            "code": playbook_code,
                            "name": playbook_name,
                            "description": playbook_description
                        })
                else:
                    logger.info(f"Flow {project.flow_id} has no playbook_sequence")
            else:
                logger.warning(f"Flow {project.flow_id} not found for project {project_id}")
        else:
            logger.warning(f"Project {project_id} has no flow_id, cannot determine playbooks")

        # Calculate progress
        if total_playbooks > 0:
            # Extract playbook_code from executions (handle both dict and object formats)
            def get_playbook_code(exec_obj):
                if isinstance(exec_obj, dict):
                    return exec_obj.get('playbook_code') or exec_obj.get('task', {}).get('execution_context', {}).get('playbook_code')
                return exec_obj.playbook_code if hasattr(exec_obj, 'playbook_code') else None

            completed_playbooks = len(set([get_playbook_code(e) for e in completed_executions if get_playbook_code(e)]))
            # Cap progress at 100% if completed exceeds total (can happen if playbooks were added after execution)
            progress_current = min(100, int((completed_playbooks / total_playbooks) * 100)) if total_playbooks > 0 else 0
            progress_label = f"{completed_playbooks}/{total_playbooks} Playbooks 完成"
            logger.info(f"[ProjectCard] Progress: {completed_playbooks}/{total_playbooks} playbooks completed, {progress_current}%")
        else:
            progress_current = 0
            progress_label = "尚未開始"

        # Get recent events for card display
        # Use the all_workspace_events we already fetched earlier
        recent_events_list = []

        # First try project events
        project_events_for_display = events_store.get_events_by_project(
            project_id=project_id,
            limit=10
        )
        recent_events_list.extend(project_events_for_display)

        # Always get workspace events that match our project executions
        # Use the all_workspace_events we already fetched earlier
        if project_executions and all_workspace_events:
            # Extract execution IDs (handle both dict and object formats)
            exec_ids = []
            for e in project_executions[:20]:
                if isinstance(e, dict):
                    exec_ids.append(e.get('id') or e.get('execution_id'))
                elif hasattr(e, 'id'):
                    exec_ids.append(e.id)
                elif hasattr(e, 'execution_id'):
                    exec_ids.append(e.execution_id)
            exec_ids = [eid for eid in exec_ids if eid]  # Filter out None values
            # Query database again to get full event data
            try:
                conn = sqlite3.connect(store.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, timestamp, actor, channel, profile_id, project_id, workspace_id,
                           event_type, payload, entity_ids
                    FROM mind_events
                    WHERE workspace_id = ?
                    AND payload LIKE '%execution_id%'
                    ORDER BY timestamp DESC
                    LIMIT 50
                ''', (workspace_id,))
                rows = cursor.fetchall()
                conn.close()

                for row in rows:
                    payload_str = row[8] if row[8] else '{}'
                    payload = json.loads(payload_str) if payload_str else {}
                    exec_id = payload.get('execution_id')

                    if exec_id and exec_id in exec_ids:
                        # Create event object compatible with get_events_by_project format
                        from types import SimpleNamespace
                        event = SimpleNamespace(
                            id=row[0],
                            timestamp=row[1],
                            actor=SimpleNamespace(value=row[2] if row[2] else 'USER'),
                            channel=row[3],
                            profile_id=row[4],
                            project_id=row[5],
                            workspace_id=row[6],
                            event_type=SimpleNamespace(value=row[7]),
                            payload=payload,
                            entity_ids=json.loads(row[9]) if row[9] else [],
                            metadata={}
                        )
                        # Avoid duplicates
                        if not any(hasattr(e, 'id') and e.id == event.id for e in recent_events_list):
                            recent_events_list.append(event)
                        if len(recent_events_list) >= 10:
                            break
            except Exception as e:
                logger.warning(f"Failed to get workspace events for card: {e}")

        # Transform events to card format
        card_events = []
        for event in recent_events_list[:5]:
            event_type = None
            playbook_code = None
            playbook_name = None
            execution_id = None
            step_index = None
            step_name = None

            if event.payload and isinstance(event.payload, dict):
                execution_id = event.payload.get('execution_id')
                playbook_code = event.payload.get('playbook_code')

                # Determine event type from event_type
                event_type_str = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                if event_type_str == 'EXECUTION_PLAN':
                    # Execution plan events indicate playbook started
                    event_type = 'playbook_started'
                elif event_type_str == 'MESSAGE':
                    # Check if it's assistant message (might indicate playbook started)
                    actor_str = event.actor.value if hasattr(event.actor, 'value') else str(event.actor)
                    if actor_str == 'ASSISTANT':
                        event_type = 'playbook_started'
                elif 'PLAYBOOK_STEP' in event_type_str or 'step' in event_type_str.lower():
                    event_type = 'step_completed'
                elif 'ARTIFACT' in event_type_str or 'artifact' in event_type_str.lower():
                    event_type = 'artifact_created'
                elif 'CONFIRMATION' in event_type_str or 'confirmation' in event_type_str.lower() or 'waiting' in event_type_str.lower():
                    event_type = 'confirmation_needed'

                # Try to get playbook name
                if playbook_code:
                    try:
                        from backend.app.services.playbook_registry import PlaybookRegistry
                        registry = PlaybookRegistry()
                        # Note: This section may need adjustment based on actual usage
                        playbook = loader.get_playbook_by_code(playbook_code, locale='zh-TW')
                        if playbook:
                            playbook_name = playbook.metadata.name if hasattr(playbook.metadata, 'name') else playbook_code
                    except:
                        playbook_name = playbook_code

                step_index = event.payload.get('step_index')
                step_name = event.payload.get('step_name')

            # Only include events with valid type, and limit metadata size
            if event_type:
                # Limit metadata to essential fields only to avoid huge payloads
                limited_metadata = {}
                if event.payload and isinstance(event.payload, dict):
                    # Only include small, essential fields
                    for key in ['execution_id', 'playbook_code', 'step_index', 'step_name']:
                        if key in event.payload:
                            limited_metadata[key] = event.payload[key]

                card_events.append({
                    "id": event.id,
                    "type": event_type,
                    "playbookCode": playbook_code or "",
                    "playbookName": playbook_name or playbook_code or "Unknown",
                    "executionId": execution_id or "",
                    "stepIndex": step_index,
                    "stepName": step_name,
                    "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
                    "metadata": limited_metadata
                })

        # Get mind lens info if available
        mind_lens_id = project.metadata.get('mind_lens_id') if project.metadata else None
        mind_lens_name = project.metadata.get('mind_lens_name') if project.metadata else None

        # Map project state to status
        status_map = {
            'open': 'active',
            'closed': 'completed',
            'archived': 'archived'
        }
        status = status_map.get(project.state, 'active')

        return {
            "projectId": project.id,
            "projectName": project.title,
            "storyThreadId": project.metadata.get('story_thread_id') if project.metadata else None,
            "mindLensId": mind_lens_id,
            "mindLensName": mind_lens_name,
            "status": status,
            "lastActivity": project.updated_at.isoformat() if hasattr(project.updated_at, 'isoformat') else str(project.updated_at),
            "stats": {
                "totalPlaybooks": total_playbooks,
                "runningExecutions": len(running_executions),
                "pendingConfirmations": len(pending_confirmations),
                "completedExecutions": len(completed_executions),
                "artifactCount": len(artifacts)
            },
            "progress": {
                "current": progress_current,
                "label": progress_label
            },
            "playbooks": playbook_list,
            "recentEvents": card_events
        }
    except PermissionError as e:
        logger.error(f"Permission error getting project card: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project card: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
