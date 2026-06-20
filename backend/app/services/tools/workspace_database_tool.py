"""Read-only database query tool for workspace-scoped data."""

import logging
from datetime import datetime
from typing import Any, Dict

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolInputSchema,
    ToolMetadata,
)
from backend.app.services.tools.workspace_tools_core import (
    parse_table_refs,
    strip_sql_comments,
    strip_sql_string_literals,
    validate_workspace_query,
)

logger = logging.getLogger(__name__)


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
        import os

        import psycopg2
        import psycopg2.extras

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
