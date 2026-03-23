"""Constants for workspace tools helper modules."""

from datetime import timedelta

RECENT_CANDIDATE_WINDOW = timedelta(minutes=5)

SQL_ALIAS_KEYWORDS = {
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

FORBIDDEN_SQL_KEYWORDS = (
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

SYSTEM_CATALOG_PATTERNS = (
    r"\bpg_",
    r"\binformation_schema\b",
    r"\bpg_catalog\b",
)
