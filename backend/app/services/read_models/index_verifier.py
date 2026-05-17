"""Database metadata checks for read-model contracts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text


def relation_exists(conn: Any, relation: str) -> bool:
    row = conn.execute(
        text("SELECT to_regclass(:relation) AS relation_name"),
        {"relation": relation},
    ).fetchone()
    return bool(row and row[0])


def relation_columns(conn: Any, relation: str) -> set[str]:
    row = conn.execute(
        text(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema = COALESCE(NULLIF(split_part(:relation, '.', 1), ''), 'public')
              AND table_name = CASE
                    WHEN position('.' in :relation) > 0 THEN split_part(:relation, '.', 2)
                    ELSE :relation
                  END
            LIMIT 1
            """
        ),
        {"relation": relation},
    ).fetchone()
    if not row:
        return set()
    schema_name, table_name = row
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    ).fetchall()
    return {str(item[0]) for item in rows}


def explain_references_forbidden_source(
    explain_text: str,
    forbidden_sources: list[dict[str, Any]],
) -> bool:
    for source in forbidden_sources:
        relation = source.get("relation")
        if isinstance(relation, str) and relation in explain_text:
            return True
    return False
