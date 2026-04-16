"""
Workspace Tools

Tools for querying execution status and workspace information.
Used by execution_status_query playbook.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime


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
from backend.app.services.tools.workspace_tools_core import (
    parse_table_refs,
    select_recent_candidates,
    strip_sql_comments,
    strip_sql_string_literals,
    task_to_payload,
    utc_now,
    validate_workspace_query,
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
                        "description": "List of candidate executions",
                    },
                    "user_query": {
                        "type": "string",
                        "description": "User's query message",
                    },
                    "conversation_context": {
                        "type": "string",
                        "description": "Conversation context",
                    },
                    "extracted_intent": {
                        "type": "object",
                        "description": "Extracted intent from user message",
                    },
                },
                required=["candidates", "user_query"],
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        candidates: List[Dict[str, Any]],
        user_query: str,
        conversation_context: str = "",
        extracted_intent: Optional[Dict[str, Any]] = None,
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
            return {
                "execution_id": candidates[0].get("execution_id")
                or candidates[0].get("id")
            }

        extracted_intent = extracted_intent or {}

        filtered_candidates = candidates
        if extracted_intent.get("playbook_code"):
            filtered_candidates = [
                c
                for c in candidates
                if c.get("playbook_code") == extracted_intent["playbook_code"]
            ]
            if len(filtered_candidates) == 1:
                return {
                    "execution_id": filtered_candidates[0].get("execution_id")
                    or filtered_candidates[0].get("id")
                }
            if len(filtered_candidates) > 1:
                candidates = filtered_candidates

        recent_candidates = select_recent_candidates(candidates, now=utc_now())

        if len(recent_candidates) == 1:
            return {
                "execution_id": recent_candidates[0].get("execution_id")
                or recent_candidates[0].get("id")
            }
        if len(recent_candidates) > 1:
            candidates = recent_candidates

        if len(candidates) == 1:
            return {
                "execution_id": candidates[0].get("execution_id")
                or candidates[0].get("id")
            }

        from backend.app.capabilities.core_llm.services.structured import (
            extract_structured,
        )

        schema = {
            "type": "object",
            "properties": {
                "execution_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["execution_id"],
        }

        candidate_summary = "\n".join(
            [
                f"{i+1}. Execution {c.get('execution_id') or c.get('id', 'unknown')}: {c.get('playbook_code', 'unknown')} "
                f"(status: {c.get('status', 'unknown')}, started: {c.get('created_at', 'unknown')})"
                for i, c in enumerate(candidates[:5])
            ]
        )

        prompt = f"""
From the following candidate executions, select the one that best matches the user query:

User query: {user_query}
Conversation context: {conversation_context}
Extracted intent: {extracted_intent}

Candidates (filtered):
{candidate_summary}

Select the best matching execution_id and explain why.
"""

        result = await extract_structured(prompt, schema)
        return {"execution_id": result["execution_id"]}


class WorkspaceQueryDatabaseTool(MindscapeTool):
    """Read-only SQL query tool for workspace data analysis.

    Security layers:
    - SELECT-only enforcement
    - Table whitelist (only workspace-scoped data tables)
    - Multi-statement blocking (no semicolons)
    - SQL comment stripping (-- and /* */)
    - System catalog/information_schema blocking
    - Mandatory workspace_id: auto-injected as WHERE filter
    - Automatic LIMIT cap (100 rows)
    - Statement timeout (10s)
    - Response payload size cap (500KB)
    - Read-only connection session
    """

    # Tables that agents are allowed to query - dynamically collected
    # from installed pack manifests (`queryable_tables` field).
    ALLOWED_TABLES: set = set()
    WORKSPACE_SCOPED_TABLES: set = set()

    MAX_ROWS = 100
    STATEMENT_TIMEOUT_MS = 10_000  # 10 seconds
    MAX_RESPONSE_BYTES = 500_000  # 500 KB
    _TABLE_SUMMARY_LIMIT = 8
    _TABLE_SUMMARY_MAX_CHARS = 140

    @classmethod
    def _collect_tables_from_registry(cls) -> tuple:
        """Collect queryable_tables from enabled pack manifests only.

        Returns (allowed_tables, workspace_scoped_tables) as sets.
        """
        try:
            from backend.app.services.capability_registry import (
                get_registry,
                load_capabilities,
            )

            registry = get_registry()
            if not registry.capabilities:
                load_capabilities()

            # Only include tables from enabled packs
            enabled_codes = set()
            try:
                from backend.app.services.stores.installed_packs_store import (
                    InstalledPacksStore,
                )

                store = InstalledPacksStore()
                enabled_codes = set(store.list_enabled_pack_ids())
            except Exception as e:
                # Strict fallback: if DB unreachable, allow no tables
                logger.warning("Could not query enabled packs: %s", e)
                enabled_codes = set()

            allowed = set()
            scoped = set()
            for cap_code, cap_info in registry.capabilities.items():
                if cap_code not in enabled_codes:
                    continue
                manifest = cap_info.get("manifest", {})
                for table in manifest.get("queryable_tables", []):
                    if isinstance(table, dict):
                        name = table.get("name", "")
                        if name:
                            allowed.add(name)
                            if table.get("workspace_scoped", True):
                                scoped.add(name)
                    elif isinstance(table, str) and table:
                        allowed.add(table)
                        scoped.add(table)  # default: workspace-scoped
            return allowed, scoped
        except Exception as e:
            logger.warning("Failed to collect queryable_tables from registry: %s", e)
            return set(), set()

    def __init__(self):
        # Re-collect on each init to reflect pack enable/disable changes
        allowed, scoped = self._collect_tables_from_registry()
        WorkspaceQueryDatabaseTool.ALLOWED_TABLES = allowed
        WorkspaceQueryDatabaseTool.WORKSPACE_SCOPED_TABLES = scoped

        table_summary = self._summarize_allowed_tables()
        metadata = ToolMetadata(
            name="workspace_query_database",
            description=(
                "Execute a read-only SQL SELECT query against registered workspace tables. "
                f"Allowed tables include: {table_summary}. "
                f"Results are limited to {self.MAX_ROWS} rows. "
                "Only SELECT statements are permitted, and workspace_id scoping is enforced automatically."
            ),
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "sql_query": {
                        "type": "string",
                        "description": (
                            "SQL SELECT query to execute. Only SELECT is allowed. "
                            "Do not include workspace_id filtering; it is added automatically. "
                            f"Allowed tables include: {table_summary}"
                        ),
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace ID (required, used for data isolation)",
                    },
                },
                required=["sql_query", "workspace_id"],
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low",
            tags=["database", "sql", "analytics", "ig"],
        )
        super().__init__(metadata)

    @classmethod
    def _summarize_allowed_tables(cls) -> str:
        """Summarize registered queryable tables without exceeding metadata limits."""
        tables = sorted(cls.ALLOWED_TABLES)
        if not tables:
            return "(none registered)"

        summary_tables = tables[: cls._TABLE_SUMMARY_LIMIT]
        summary = ", ".join(summary_tables)
        remaining = len(tables) - len(summary_tables)
        if remaining > 0:
            summary = f"{summary}, +{remaining} more"

        if len(summary) <= cls._TABLE_SUMMARY_MAX_CHARS:
            return summary

        trimmed = summary[: cls._TABLE_SUMMARY_MAX_CHARS - 3].rstrip(", ")
        if "," in trimmed:
            trimmed = trimmed.rsplit(",", 1)[0]
        trimmed = trimmed.rstrip(", ")
        return f"{trimmed}..."

    def _strip_comments(self, sql: str) -> str:
        """Remove SQL comments to prevent injection via comments."""
        return strip_sql_comments(sql)

    @staticmethod
    def _strip_string_literals(sql: str) -> str:
        """Replace string literals with placeholders for safe keyword checking.

        Prevents false positives when forbidden keywords appear inside
        quoted string values (e.g. WHERE bio LIKE '%copy%').
        """
        return strip_sql_string_literals(sql)

    @staticmethod
    def _parse_table_refs(sql: str) -> list:
        """Parse table references with optional aliases from FROM/JOIN clauses.

        Returns list of (table_name, alias_or_table_name) tuples.
        Examples:
            FROM ig_accounts_flat          -> [("ig_accounts_flat", "ig_accounts_flat")]
            FROM ig_accounts_flat AS a     -> [("ig_accounts_flat", "a")]
            FROM ig_accounts_flat a        -> [("ig_accounts_flat", "a")]
            JOIN ig_posts p ON ...         -> [("ig_posts", "p")]
        """
        return parse_table_refs(sql)

    def _validate_query(self, sql_query: str, workspace_id: str) -> str:
        """Validate and sanitize the SQL query.

        Raises ValueError for disallowed operations or tables.
        Returns the sanitized query with workspace_id filter and LIMIT enforced.
        """
        return validate_workspace_query(
            sql_query,
            workspace_id,
            allowed_tables=self.ALLOWED_TABLES,
            workspace_scoped_tables=self.WORKSPACE_SCOPED_TABLES,
            max_rows=self.MAX_ROWS,
        )

    async def execute(self, sql_query: str, workspace_id: str = "") -> Dict[str, Any]:
        """Execute a read-only SQL query and return results."""
        import psycopg2
        import psycopg2.extras
        import os

        validated_query = self._validate_query(sql_query, workspace_id)

        # Follow core convention: DATABASE_URL_CORE takes priority
        db_url = (
            os.environ.get("DATABASE_URL_CORE")
            or os.environ.get("DATABASE_URL")
            or "postgresql://mindscape:mindscape_password@postgres:5432/mindscape_core"
        )

        conn = psycopg2.connect(db_url)
        try:
            conn.set_session(readonly=True, autocommit=True)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Set statement timeout to prevent long-running queries
            cur.execute(f"SET statement_timeout = {self.STATEMENT_TIMEOUT_MS}")

            # Use parameterized query for workspace_id
            # Count %s placeholders (one per scoped table in JOINs)
            param_count = validated_query.count("%s")
            if param_count > 0:
                cur.execute(
                    validated_query, tuple(workspace_id for _ in range(param_count))
                )
            else:
                cur.execute(validated_query)

            rows = cur.fetchall()
            cur.close()

            columns = list(rows[0].keys()) if rows else []
            data = [dict(r) for r in rows]

            # Convert non-serializable types
            for row in data:
                for key, val in row.items():
                    if isinstance(val, datetime):
                        row[key] = val.isoformat()
                    elif not isinstance(
                        val, (str, int, float, bool, type(None), list, dict)
                    ):
                        row[key] = str(val)

            result = {
                "columns": columns,
                "rows": data,
                "row_count": len(data),
                "query": validated_query,
                "workspace_id": workspace_id,
            }

            # Cap response payload size
            import json as _json

            payload = _json.dumps(result, default=str)
            if len(payload) > self.MAX_RESPONSE_BYTES:
                # Truncate rows until under limit
                while (
                    data
                    and len(_json.dumps(result, default=str)) > self.MAX_RESPONSE_BYTES
                ):
                    data.pop()
                result["rows"] = data
                result["row_count"] = len(data)
                result["truncated"] = True

            return result

        except psycopg2.Error as e:
            raise RuntimeError(f"SQL error: {e}")
        finally:
            conn.close()


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
