"""
Workspace Tools

Tools for querying execution status and workspace information.
Used by execution_status_query playbook.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema, ToolCategory

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
                    "execution_id": {
                        "type": "string",
                        "description": "Execution ID"
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace ID"
                    }
                },
                required=["execution_id", "workspace_id"]
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(self, execution_id: str, workspace_id: str) -> Dict[str, Any]:
        """Get execution status and details"""
        from backend.app.models.workspace import ExecutionSession

        store = MindscapeStore()
        tasks_store = TasksStore(store.db_path)

        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            raise ValueError(f"Execution {execution_id} not found")

        if task.workspace_id != workspace_id:
            raise PermissionError(f"Execution belongs to different workspace")

        execution = ExecutionSession.from_task(task)
        return execution.model_dump() if hasattr(execution, 'model_dump') else execution


class WorkspaceGetExecutionStepsTool(MindscapeTool):
    """Get execution steps"""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_get_execution_steps",
            description="Get execution steps by execution_id",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "execution_id": {
                        "type": "string",
                        "description": "Execution ID"
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace ID"
                    }
                },
                required=["execution_id", "workspace_id"]
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(self, execution_id: str, workspace_id: str) -> List[Dict[str, Any]]:
        """Get execution steps"""
        store = MindscapeStore()
        events = store.get_events_by_workspace(workspace_id=workspace_id, limit=1000)

        playbook_step_events = [
            e for e in events
            if hasattr(e, 'event_type') and e.event_type.value == 'playbook_step'
            and e.payload.get("execution_id") == execution_id
        ]

        return [e.payload if isinstance(e.payload, dict) else {} for e in playbook_step_events]


class WorkspaceListExecutionsTool(MindscapeTool):
    """List executions with filters"""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_list_executions",
            description="List executions with filters (status, playbook_code, since)",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace ID"
                    },
                    "status": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by status (pending, running, succeeded, failed, cancelled)"
                    },
                    "playbook_code": {
                        "type": "string",
                        "description": "Filter by playbook code"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of results"
                    },
                    "since": {
                        "type": "string",
                        "format": "date-time",
                        "description": "Only return executions started after this time (ISO datetime)"
                    }
                },
                required=["workspace_id"]
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        workspace_id: str,
        status: Optional[List[str]] = None,
        playbook_code: Optional[str] = None,
        limit: int = 20,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List executions with filters

        Returns:
            List of executions, sorted by created_at DESC (most recent first)
        """
        from backend.app.models.workspace import ExecutionSession

        store = MindscapeStore()
        tasks_store = TasksStore(store.db_path)

        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except Exception as e:
                logger.warning(f"Failed to parse since datetime: {e}")

        all_tasks = tasks_store.list_tasks_by_workspace(
            workspace_id,
            limit=limit * 2
        )

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
                executions.append(execution.model_dump() if hasattr(execution, 'model_dump') else execution)
            except Exception as e:
                logger.warning(f"Failed to convert task {task.id} to ExecutionSession: {e}")

        return executions


class WorkspacePickRelevantExecutionTool(MindscapeTool):
    """Pick the most relevant execution from candidates"""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_pick_relevant_execution",
            description="Pick the most relevant execution from candidates using heuristics and LLM",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "candidates": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of candidate executions"
                    },
                    "user_query": {
                        "type": "string",
                        "description": "User's query message"
                    },
                    "conversation_context": {
                        "type": "string",
                        "description": "Conversation context"
                    },
                    "extracted_intent": {
                        "type": "object",
                        "description": "Extracted intent from user message"
                    }
                },
                required=["candidates", "user_query"]
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        candidates: List[Dict[str, Any]],
        user_query: str,
        conversation_context: str = "",
        extracted_intent: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Pick the most relevant execution from candidates

        Heuristics (applied before LLM):
        1. Filter by playbook_code if extracted_intent has it
        2. Same conversation thread (recently started) - highest priority
        3. Same playbook_code, most recent - second priority
        4. If still multiple candidates, use LLM to disambiguate
        """
        if not candidates:
            raise ValueError("No candidate executions found")

        if len(candidates) == 1:
            return {"execution_id": candidates[0].get("execution_id") or candidates[0].get("id")}

        extracted_intent = extracted_intent or {}

        filtered_candidates = candidates
        if extracted_intent.get("playbook_code"):
            filtered_candidates = [
                c for c in candidates
                if c.get("playbook_code") == extracted_intent["playbook_code"]
            ]
            if len(filtered_candidates) == 1:
                return {"execution_id": filtered_candidates[0].get("execution_id") or filtered_candidates[0].get("id")}
            if len(filtered_candidates) > 1:
                candidates = filtered_candidates

        now = datetime.utcnow()
        recent_threshold = now - timedelta(minutes=5)

        recent_candidates = []
        for c in candidates:
            created_at = c.get("created_at")
            if created_at:
                try:
                    if isinstance(created_at, str):
                        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    else:
                        created_dt = created_at
                    if created_dt > recent_threshold:
                        recent_candidates.append(c)
                except Exception:
                    pass

        if len(recent_candidates) == 1:
            return {"execution_id": recent_candidates[0].get("execution_id") or recent_candidates[0].get("id")}
        if len(recent_candidates) > 1:
            candidates = recent_candidates

        if len(candidates) == 1:
            return {"execution_id": candidates[0].get("execution_id") or candidates[0].get("id")}

        from backend.app.capabilities.core_llm.services.structured import extract_structured

        schema = {
            "type": "object",
            "properties": {
                "execution_id": {"type": "string"},
                "reason": {"type": "string"}
            },
            "required": ["execution_id"]
        }

        candidate_summary = "\n".join([
            f"{i+1}. Execution {c.get('execution_id') or c.get('id', 'unknown')}: {c.get('playbook_code', 'unknown')} "
            f"(status: {c.get('status', 'unknown')}, started: {c.get('created_at', 'unknown')})"
            for i, c in enumerate(candidates[:5])
        ])

        prompt = f"""
從以下候選 executions 中選出最符合用戶查詢的：

用戶查詢：{user_query}
對話上下文：{conversation_context}
提取的意圖：{extracted_intent}

候選列表（已過濾）：
{candidate_summary}

請選出最符合的 execution_id 並說明原因。
"""

        result = await extract_structured(prompt, schema)
        return {"execution_id": result["execution_id"]}


def create_workspace_tools() -> List[MindscapeTool]:
    """Create all workspace tools"""
    return [
        WorkspaceGetExecutionTool(),
        WorkspaceGetExecutionStepsTool(),
        WorkspaceListExecutionsTool(),
        WorkspacePickRelevantExecutionTool()
    ]


def get_workspace_tool_by_name(tool_name: str) -> Optional[MindscapeTool]:
    """Get workspace tool by name"""
    tools = {
        "workspace.get_execution": WorkspaceGetExecutionTool(),
        "workspace.get_execution_steps": WorkspaceGetExecutionStepsTool(),
        "workspace.list_executions": WorkspaceListExecutionsTool(),
        "workspace.pick_relevant_execution": WorkspacePickRelevantExecutionTool(),
        "workspace_get_execution": WorkspaceGetExecutionTool(),
        "workspace_get_execution_steps": WorkspaceGetExecutionStepsTool(),
        "workspace_list_executions": WorkspaceListExecutionsTool(),
        "workspace_pick_relevant_execution": WorkspacePickRelevantExecutionTool()
    }
    return tools.get(tool_name)

