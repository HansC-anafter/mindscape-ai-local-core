"""
Workspace Tools

Tools for querying execution status and workspace information.
Used by execution_status_query playbook.
"""

import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


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

logger = logging.getLogger(__name__)


def _task_to_payload(task: Any) -> Dict[str, Any]:
    if hasattr(task, "model_dump"):
        return task.model_dump(mode="json")
    if isinstance(task, dict):
        return dict(task)
    if hasattr(task, "__dict__"):
        return dict(task.__dict__)
    return {}


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
            key=lambda task: getattr(task, "created_at", _utc_now()), reverse=True
        )
        return [
            project_execution_for_api(
                _task_to_payload(task),
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

        payload = _task_to_payload(task)
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

        now = _utc_now()
        recent_threshold = now - timedelta(minutes=5)

        recent_candidates = []
        for c in candidates:
            created_at = c.get("created_at")
            if created_at:
                try:
                    if isinstance(created_at, str):
                        created_dt = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        )
                    else:
                        created_dt = created_at
                    if created_dt > recent_threshold:
                        recent_candidates.append(c)
                except Exception:
                    pass

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

        table_list = ", ".join(sorted(self.ALLOWED_TABLES)) or "(none registered)"
        metadata = ToolMetadata(
            name="workspace_query_database",
            description=(
                "Execute a read-only SQL SELECT query against the workspace database. "
                "Use this tool to query and analyze data such as IG accounts, follow edges, "
                "posts, and generated personas. "
                f"Allowed tables: {table_list}. "
                f"Results are limited to {self.MAX_ROWS} rows. "
                "Only SELECT statements are permitted. "
                "workspace_id is required to scope results to the current workspace."
            ),
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "sql_query": {
                        "type": "string",
                        "description": (
                            "SQL SELECT query to execute. Only SELECT is allowed. "
                            "Do NOT include workspace_id filtering -- it is added automatically. "
                            f"Allowed tables: {table_list}"
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

    def _strip_comments(self, sql: str) -> str:
        """Remove SQL comments to prevent injection via comments."""
        # Remove single-line comments (-- ...)
        sql = re.sub(r"--[^\n]*", "", sql)
        # Remove multi-line comments (/* ... */)
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        return sql.strip()

    @staticmethod
    def _strip_string_literals(sql: str) -> str:
        """Replace string literals with placeholders for safe keyword checking.

        Prevents false positives when forbidden keywords appear inside
        quoted string values (e.g. WHERE bio LIKE '%copy%').
        """
        return re.sub(r"'[^']*'", "'__STR__'", sql)

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
        # Match: FROM/JOIN table [AS] [alias]
        # alias is a single word that is NOT a SQL keyword
        sql_keywords = {
            "ON",
            "WHERE",
            "SET",
            "AND",
            "OR",
            "LEFT",
            "RIGHT",
            "INNER",
            "OUTER",
            "CROSS",
            "FULL",
            "JOIN",
            "GROUP",
            "ORDER",
            "HAVING",
            "LIMIT",
            "OFFSET",
            "UNION",
            "SELECT",
            "FROM",
            "AS",
            "NATURAL",
        }
        pattern = r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*))?"
        refs = []
        for m in re.finditer(pattern, sql, re.IGNORECASE):
            table = m.group(1).lower()
            alias_candidate = m.group(2)
            if alias_candidate and alias_candidate.upper() not in sql_keywords:
                alias = alias_candidate
            else:
                alias = table
            refs.append((table, alias))
        return refs

    def _validate_query(self, sql_query: str, workspace_id: str) -> str:
        """Validate and sanitize the SQL query.

        Raises ValueError for disallowed operations or tables.
        Returns the sanitized query with workspace_id filter and LIMIT enforced.
        """
        if not workspace_id or not workspace_id.strip():
            raise ValueError("workspace_id is required for data isolation")

        # Strip comments first to prevent injection
        cleaned = self._strip_comments(sql_query)

        # Strip trailing semicolon (valid single-statement SQL) before
        # checking for multi-statement injection attempts
        cleaned = cleaned.rstrip(";").strip()
        if ";" in cleaned:
            raise ValueError("Multi-statement queries are not allowed")

        normalized = cleaned.strip()
        upper = normalized.upper()

        # Only SELECT is allowed
        if not upper.startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")

        # Strip string literals before keyword checking to avoid false positives
        # e.g. WHERE bio LIKE '%copy%' should NOT trigger COPY block
        sanitized_for_check = self._strip_string_literals(normalized).upper()

        # Block write operations (checked against string-literal-stripped version)
        forbidden = (
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "ALTER",
            "CREATE",
            "TRUNCATE",
            "GRANT",
            "REVOKE",
            "EXEC",
            "EXECUTE",
            "COPY",
            "VACUUM",
            "REINDEX",
            "CLUSTER",
        )
        for keyword in forbidden:
            if re.search(rf"\b{keyword}\b", sanitized_for_check):
                raise ValueError(f"Forbidden SQL keyword: {keyword}")

        # Block system catalog access (checked against stripped version)
        system_patterns = (
            r"\bpg_",
            r"\binformation_schema\b",
            r"\bpg_catalog\b",
        )
        for pattern in system_patterns:
            if re.search(pattern, sanitized_for_check, re.IGNORECASE):
                raise ValueError("Access to system catalogs is not allowed")

        # Parse table references with aliases
        table_refs = self._parse_table_refs(normalized)
        referenced_tables = {t for t, _ in table_refs}

        if not referenced_tables:
            raise ValueError("Query must reference at least one allowed table")

        disallowed = referenced_tables - self.ALLOWED_TABLES
        if disallowed:
            raise ValueError(
                f"Disallowed table(s): {', '.join(sorted(disallowed))}. "
                f"Allowed: {', '.join(sorted(self.ALLOWED_TABLES))}"
            )

        # Build workspace_id filters for ALL scoped tables (not just first)
        # Uses alias when present so JOINed queries work correctly
        scoped_refs = [
            (table, alias)
            for table, alias in table_refs
            if table in self.WORKSPACE_SCOPED_TABLES
        ]
        if scoped_refs:
            # Escape existing % in user SQL to %% before injecting %s placeholders
            # Prevents psycopg2 from treating user % (e.g. LIKE '%foo%') as format specs
            normalized = normalized.replace("%", "%%")

            ws_conditions = [f"{alias}.workspace_id = %s" for _, alias in scoped_refs]
            ws_filter = " AND ".join(ws_conditions)

            if " WHERE " in normalized.upper():
                normalized = re.sub(
                    r"\bWHERE\b",
                    f"WHERE {ws_filter} AND",
                    normalized,
                    count=1,
                    flags=re.IGNORECASE,
                )
            else:
                insert_point = len(normalized)
                for clause in ("ORDER BY", "GROUP BY", "HAVING", "LIMIT"):
                    idx = normalized.upper().find(clause)
                    if idx != -1 and idx < insert_point:
                        insert_point = idx
                normalized = (
                    normalized[:insert_point].rstrip()
                    + f" WHERE {ws_filter} "
                    + normalized[insert_point:]
                )

        # Enforce LIMIT
        if "LIMIT" not in normalized.upper():
            normalized += f" LIMIT {self.MAX_ROWS}"
        else:
            limit_match = re.search(r"LIMIT\s+(\d+)", normalized, re.IGNORECASE)
            if limit_match and int(limit_match.group(1)) > self.MAX_ROWS:
                normalized = re.sub(
                    r"LIMIT\s+\d+",
                    f"LIMIT {self.MAX_ROWS}",
                    normalized,
                    flags=re.IGNORECASE,
                )

        return normalized

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
