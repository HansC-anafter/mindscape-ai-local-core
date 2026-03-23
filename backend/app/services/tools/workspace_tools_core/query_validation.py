"""SQL validation helpers for WorkspaceQueryDatabaseTool."""

from __future__ import annotations

import re
from typing import Iterable

from .constants import (
    FORBIDDEN_SQL_KEYWORDS,
    SQL_ALIAS_KEYWORDS,
    SYSTEM_CATALOG_PATTERNS,
)
from .errors import WorkspaceQueryValidationError
from .types import TableReference


def strip_sql_comments(sql: str) -> str:
    """Remove SQL comments to prevent injection via comments."""
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql.strip()


def strip_sql_string_literals(sql: str) -> str:
    """Replace SQL string literals with placeholders for safe keyword checks."""
    return re.sub(r"'[^']*'", "'__STR__'", sql)


def parse_table_refs(sql: str) -> list[TableReference]:
    """Parse FROM/JOIN table references with optional aliases."""
    pattern = (
        r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        r"(?:\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*))?"
    )
    refs: list[TableReference] = []
    for match in re.finditer(pattern, sql, re.IGNORECASE):
        table = match.group(1).lower()
        alias_candidate = match.group(2)
        if alias_candidate and alias_candidate.upper() not in SQL_ALIAS_KEYWORDS:
            alias = alias_candidate
        else:
            alias = table
        refs.append((table, alias))
    return refs


def validate_workspace_query(
    sql_query: str,
    workspace_id: str,
    *,
    allowed_tables: Iterable[str],
    workspace_scoped_tables: Iterable[str],
    max_rows: int,
) -> str:
    """Validate and sanitize a workspace-scoped read-only SQL query."""
    if not workspace_id or not workspace_id.strip():
        raise WorkspaceQueryValidationError(
            "workspace_id is required for data isolation"
        )

    cleaned = strip_sql_comments(sql_query).rstrip(";").strip()
    if ";" in cleaned:
        raise WorkspaceQueryValidationError("Multi-statement queries are not allowed")

    normalized = cleaned.strip()
    upper = normalized.upper()
    if not upper.startswith("SELECT"):
        raise WorkspaceQueryValidationError("Only SELECT queries are allowed")

    sanitized_for_check = strip_sql_string_literals(normalized).upper()
    for keyword in FORBIDDEN_SQL_KEYWORDS:
        if re.search(rf"\b{keyword}\b", sanitized_for_check):
            raise WorkspaceQueryValidationError(f"Forbidden SQL keyword: {keyword}")

    for pattern in SYSTEM_CATALOG_PATTERNS:
        if re.search(pattern, sanitized_for_check, re.IGNORECASE):
            raise WorkspaceQueryValidationError(
                "Access to system catalogs is not allowed"
            )

    allowed_tables_set = set(allowed_tables)
    scoped_tables_set = set(workspace_scoped_tables)
    table_refs = parse_table_refs(normalized)
    referenced_tables = {table for table, _ in table_refs}
    if not referenced_tables:
        raise WorkspaceQueryValidationError(
            "Query must reference at least one allowed table"
        )

    disallowed = referenced_tables - allowed_tables_set
    if disallowed:
        allowed = ", ".join(sorted(allowed_tables_set))
        blocked = ", ".join(sorted(disallowed))
        raise WorkspaceQueryValidationError(
            f"Disallowed table(s): {blocked}. Allowed: {allowed}"
        )

    scoped_refs = [
        (table, alias)
        for table, alias in table_refs
        if table in scoped_tables_set
    ]
    if scoped_refs:
        normalized = normalized.replace("%", "%%")
        workspace_filter = " AND ".join(
            f"{alias}.workspace_id = %s" for _, alias in scoped_refs
        )
        if " WHERE " in normalized.upper():
            normalized = re.sub(
                r"\bWHERE\b",
                f"WHERE {workspace_filter} AND",
                normalized,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            insert_point = len(normalized)
            for clause in ("ORDER BY", "GROUP BY", "HAVING", "LIMIT"):
                index = normalized.upper().find(clause)
                if index != -1 and index < insert_point:
                    insert_point = index
            normalized = (
                normalized[:insert_point].rstrip()
                + f" WHERE {workspace_filter} "
                + normalized[insert_point:]
            )

    if "LIMIT" not in normalized.upper():
        normalized += f" LIMIT {max_rows}"
    else:
        limit_match = re.search(r"LIMIT\s+(\d+)", normalized, re.IGNORECASE)
        if limit_match and int(limit_match.group(1)) > max_rows:
            normalized = re.sub(
                r"LIMIT\s+\d+",
                f"LIMIT {max_rows}",
                normalized,
                flags=re.IGNORECASE,
            )

    return normalized
