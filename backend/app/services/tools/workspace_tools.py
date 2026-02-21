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
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolInputSchema,
    ToolCategory,
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
        tasks_store = TasksStore(store.db_path)

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
        tasks_store = TasksStore(store.db_path)

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

    # Tables that agents are allowed to query
    ALLOWED_TABLES = {
        "ig_accounts_flat",
        "ig_account_profiles",
        "ig_follow_edges",
        "ig_posts",
        "ig_generated_personas",
    }

    # Tables that have a workspace_id column for isolation
    WORKSPACE_SCOPED_TABLES = {
        "ig_accounts_flat",
        "ig_account_profiles",
        "ig_follow_edges",
        "ig_posts",
        "ig_generated_personas",
    }

    MAX_ROWS = 100
    STATEMENT_TIMEOUT_MS = 10_000  # 10 seconds
    MAX_RESPONSE_BYTES = 500_000  # 500 KB

    def __init__(self):
        table_list = ", ".join(sorted(self.ALLOWED_TABLES))
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

        # Block multi-statement queries (no semicolons allowed)
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
        WorkspacePickRelevantExecutionTool(),
        WorkspaceQueryDatabaseTool(),
    ]


def get_workspace_tool_by_name(tool_name: str) -> Optional[MindscapeTool]:
    """Get workspace tool by name"""
    tools = {
        "workspace.get_execution": WorkspaceGetExecutionTool(),
        "workspace.get_execution_steps": WorkspaceGetExecutionStepsTool(),
        "workspace.list_executions": WorkspaceListExecutionsTool(),
        "workspace.pick_relevant_execution": WorkspacePickRelevantExecutionTool(),
        "workspace.query_database": WorkspaceQueryDatabaseTool(),
        "workspace_get_execution": WorkspaceGetExecutionTool(),
        "workspace_get_execution_steps": WorkspaceGetExecutionStepsTool(),
        "workspace_list_executions": WorkspaceListExecutionsTool(),
        "workspace_pick_relevant_execution": WorkspacePickRelevantExecutionTool(),
        "workspace_query_database": WorkspaceQueryDatabaseTool(),
    }
    return tools.get(tool_name)


# Auto-register tools when module is imported
def _auto_register():
    """Auto-register workspace tools when module is imported."""
    from backend.app.services.tools.registry import register_workspace_tools

    register_workspace_tools()


_auto_register()
