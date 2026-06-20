"""
Workspace Tools

Tools for querying execution status and workspace information.
Used by execution_status_query playbook.
"""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional


from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.task_execution_projection import (
    build_remote_execution_summary,
    project_execution_for_api,
)
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolInputSchema,
    ToolCategory,
)
from backend.app.services.tools.workspace_database_tool import WorkspaceQueryDatabaseTool
from backend.app.services.tools.workspace_execution_picker_tool import (
    WorkspacePickRelevantExecutionTool,
)
from backend.app.services.tools.workspace_tools_core import (
    task_to_payload,
    utc_now,
)

logger = logging.getLogger(__name__)


class WorkspaceGetExecutionTool(MindscapeTool):
    """Get execution status and details"""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_get_execution",
            description="Get execution status and details by execution_id",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "execution_id": {"type": "string", "description": "Execution ID"},
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                },
                required=["execution_id", "workspace_id"],
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(self, execution_id: str, workspace_id: str) -> Dict[str, Any]:
        """Get execution status and details"""
        from backend.app.models.workspace import ExecutionSession

        store = MindscapeStore()
        tasks_store = TasksStore()

        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            raise ValueError(f"Execution {execution_id} not found")

        if task.workspace_id != workspace_id:
            raise PermissionError(f"Execution belongs to different workspace")

        execution = ExecutionSession.from_task(task)
        return execution.model_dump() if hasattr(execution, "model_dump") else execution


class WorkspaceGetExecutionStepsTool(MindscapeTool):
    """Get execution steps"""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_get_execution_steps",
            description="Get execution steps by execution_id",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "execution_id": {"type": "string", "description": "Execution ID"},
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                },
                required=["execution_id", "workspace_id"],
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self, execution_id: str, workspace_id: str
    ) -> List[Dict[str, Any]]:
        """Get execution steps"""
        store = MindscapeStore()
        events = store.get_events_by_workspace(workspace_id=workspace_id, limit=1000)

        playbook_step_events = [
            e
            for e in events
            if hasattr(e, "event_type")
            and e.event_type.value == "playbook_step"
            and e.payload.get("execution_id") == execution_id
        ]

        return [
            e.payload if isinstance(e.payload, dict) else {}
            for e in playbook_step_events
        ]


class WorkspaceListExecutionsTool(MindscapeTool):
    """List executions with filters"""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_list_executions",
            description="List executions with filters (status, playbook_code, since)",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "status": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by status (pending, running, succeeded, failed, cancelled)",
                    },
                    "playbook_code": {
                        "type": "string",
                        "description": "Filter by playbook code",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of results",
                    },
                    "since": {
                        "type": "string",
                        "format": "date-time",
                        "description": "Only return executions started after this time (ISO datetime)",
                    },
                },
                required=["workspace_id"],
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        workspace_id: str,
        status: Optional[List[str]] = None,
        playbook_code: Optional[str] = None,
        limit: int = 20,
        since: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List executions with filters

        Returns:
            List of executions, sorted by created_at DESC (most recent first)
        """
        from backend.app.models.workspace import ExecutionSession

        store = MindscapeStore()
        tasks_store = TasksStore()

        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except Exception as e:
                logger.warning(f"Failed to parse since datetime: {e}")

        all_tasks = tasks_store.list_tasks_by_workspace(workspace_id, limit=limit * 2)

        filtered_tasks = []
        for task in all_tasks:
            if task.execution_context is None:
                continue

            if status and task.status.value not in status:
                continue

            if playbook_code and task.pack_id != playbook_code:
                continue

            if since_dt and task.created_at < since_dt:
                continue

            filtered_tasks.append(task)
            if len(filtered_tasks) >= limit:
                break

        filtered_tasks.sort(key=lambda t: t.created_at, reverse=True)

        executions = []
        for task in filtered_tasks:
            try:
                execution = ExecutionSession.from_task(task)
                executions.append(
                    execution.model_dump()
                    if hasattr(execution, "model_dump")
                    else execution
                )
            except Exception as e:
                logger.warning(
                    f"Failed to convert task {task.id} to ExecutionSession: {e}"
                )

        return executions


class WorkspaceListChildExecutionsTool(MindscapeTool):
    """List child executions for a parent execution."""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_list_child_executions",
            description="List child executions for a parent execution_id, including remote summary metadata",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "parent_execution_id": {
                        "type": "string",
                        "description": "Parent execution ID",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of child executions",
                    },
                },
                required=["workspace_id", "parent_execution_id"],
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self, workspace_id: str, parent_execution_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        tasks_store = TasksStore()
        limit = max(1, min(int(limit or 20), 100))
        candidates = tasks_store.list_tasks_by_workspace(
            workspace_id=workspace_id,
            limit=max(limit * 4, 50),
        )
        child_tasks = [
            task for task in candidates if task.parent_execution_id == parent_execution_id
        ]
        child_tasks.sort(
            key=lambda task: getattr(task, "created_at", utc_now()), reverse=True
        )
        return [
            project_execution_for_api(
                task_to_payload(task),
                queue_position=None,
                queue_total=None,
            )
            for task in child_tasks[:limit]
        ]


class WorkspaceGetExecutionRemoteSummaryTool(MindscapeTool):
    """Get remote execution summary for a single execution."""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_get_execution_remote_summary",
            description="Get remote execution / replay summary for one execution_id",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "execution_id": {"type": "string", "description": "Execution ID"},
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                },
                required=["execution_id", "workspace_id"],
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(self, execution_id: str, workspace_id: str) -> Dict[str, Any]:
        tasks_store = TasksStore()
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            raise ValueError(f"Execution {execution_id} not found")
        if task.workspace_id != workspace_id:
            raise PermissionError("Execution belongs to different workspace")

        payload = task_to_payload(task)
        return {
            "execution_id": payload.get("execution_id") or payload.get("id"),
            "workspace_id": workspace_id,
            "status": (
                task.status.value if hasattr(task.status, "value") else str(task.status)
            ),
            "remote_execution_summary": build_remote_execution_summary(payload),
        }


class WorkspaceContinueExecutionTool(MindscapeTool):
    """Continue a paused/waiting execution via the existing playbook runner."""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_continue_execution",
            description="Continue a paused or waiting execution using the existing playbook runner",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "execution_id": {"type": "string", "description": "Execution ID"},
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "user_message": {
                        "type": "string",
                        "description": "Driver message used to continue the execution",
                    },
                    "profile_id": {
                        "type": "string",
                        "description": "Profile ID for provider selection",
                        "default": "default-user",
                    },
                },
                required=["execution_id", "workspace_id", "user_message"],
            ),
            category=ToolCategory.AUTOMATION,
            source_type="builtin",
            provider="workspace",
            danger_level="medium",
        )
        super().__init__(metadata)

    async def execute(
        self,
        execution_id: str,
        workspace_id: str,
        user_message: str,
        profile_id: str = "default-user",
    ) -> Dict[str, Any]:
        tasks_store = TasksStore()
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            raise ValueError(f"Execution {execution_id} not found")
        if task.workspace_id != workspace_id:
            raise PermissionError("Execution belongs to different workspace")

        from backend.app.services.playbook_runner import PlaybookRunner

        result = await PlaybookRunner().continue_playbook_execution(
            execution_id=execution_id,
            user_message=user_message,
            profile_id=profile_id,
        )
        return {
            "execution_id": result.get("execution_id") or execution_id,
            "playbook_code": result.get("playbook_code"),
            "message": result.get("message"),
            "is_complete": result.get("is_complete"),
            "plan_length": len(result.get("plan") or []),
        }


class WorkspaceResendRemoteStepTool(MindscapeTool):
    """Replay a remote workflow-step child execution."""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_resend_remote_step",
            description="Resend a remote workflow-step child execution using the stored remote payload",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "task_id": {"type": "string", "description": "Child task ID"},
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "target_device_id": {
                        "type": "string",
                        "description": "Optional override target GPU/VM device ID",
                    },
                },
                required=["task_id", "workspace_id"],
            ),
            category=ToolCategory.AUTOMATION,
            source_type="builtin",
            provider="workspace",
            danger_level="medium",
        )
        super().__init__(metadata)

    async def execute(
        self,
        task_id: str,
        workspace_id: str,
        target_device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        tasks_store = TasksStore()
        task = tasks_store.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        if task.workspace_id != workspace_id:
            raise PermissionError("Task belongs to different workspace")

        from backend.app.services.cloud_connector.connector import CloudConnector
        from backend.app.services.remote_step_resend_service import (
            resend_remote_workflow_step_child_task,
        )

        return await resend_remote_workflow_step_child_task(
            task=task,
            workspace_id=workspace_id,
            connector=CloudConnector(),
            target_device_id=target_device_id,
        )


def create_workspace_tools() -> List[MindscapeTool]:
    """Create all workspace tools"""
    return [
        WorkspaceGetExecutionTool(),
        WorkspaceGetExecutionStepsTool(),
        WorkspaceListExecutionsTool(),
        WorkspaceListChildExecutionsTool(),
        WorkspaceGetExecutionRemoteSummaryTool(),
        WorkspaceContinueExecutionTool(),
        WorkspaceResendRemoteStepTool(),
        WorkspacePickRelevantExecutionTool(),
        WorkspaceQueryDatabaseTool(),
    ]


def get_workspace_tool_by_name(tool_name: str) -> Optional[MindscapeTool]:
    """Get workspace tool by name"""
    tools = {
        "workspace.get_execution": WorkspaceGetExecutionTool(),
        "workspace.get_execution_steps": WorkspaceGetExecutionStepsTool(),
        "workspace.list_executions": WorkspaceListExecutionsTool(),
        "workspace.list_child_executions": WorkspaceListChildExecutionsTool(),
        "workspace.get_execution_remote_summary": WorkspaceGetExecutionRemoteSummaryTool(),
        "workspace.continue_execution": WorkspaceContinueExecutionTool(),
        "workspace.resend_remote_step": WorkspaceResendRemoteStepTool(),
        "workspace.pick_relevant_execution": WorkspacePickRelevantExecutionTool(),
        "workspace.query_database": WorkspaceQueryDatabaseTool(),
        "workspace_get_execution": WorkspaceGetExecutionTool(),
        "workspace_get_execution_steps": WorkspaceGetExecutionStepsTool(),
        "workspace_list_executions": WorkspaceListExecutionsTool(),
        "workspace_list_child_executions": WorkspaceListChildExecutionsTool(),
        "workspace_get_execution_remote_summary": WorkspaceGetExecutionRemoteSummaryTool(),
        "workspace_continue_execution": WorkspaceContinueExecutionTool(),
        "workspace_resend_remote_step": WorkspaceResendRemoteStepTool(),
        "workspace_pick_relevant_execution": WorkspacePickRelevantExecutionTool(),
        "workspace_query_database": WorkspaceQueryDatabaseTool(),
    }
    return tools.get(tool_name)


# Registration is handled by _get_builtin_tools() in tool_list_service.py.
# Do NOT auto-register here; import-time side effects cause ordering bugs.
