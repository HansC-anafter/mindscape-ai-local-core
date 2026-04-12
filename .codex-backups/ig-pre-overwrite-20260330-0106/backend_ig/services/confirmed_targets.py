"""Helpers for IG confirmed target totals and indexing."""

from __future__ import annotations

from typing import Iterable, Optional

from capabilities.ig.source_filters import CONFIRMED_SOURCE_CONTEXT

CONFIRMED_TARGETS_TABLE = "ig_confirmed_targets"
_SEED_PLACEHOLDER_PREFIX = "__seed_placeholder__"


def normalize_target_handle(value: Optional[str]) -> str:
    return (value or "").strip().lstrip("@").lower()


def is_confirmed_target_source_context(value: Optional[str]) -> bool:
    normalized = (value or "").strip().lower()
    return normalized in {"", CONFIRMED_SOURCE_CONTEXT}


def should_use_confirmed_targets_total_fast_path(
    *,
    seed: Optional[str] = None,
    source_handle: Optional[str] = None,
    search: Optional[str] = None,
) -> bool:
    return not seed and not source_handle and not search


def confirmed_targets_table_exists(conn) -> bool:
    from sqlalchemy import text

    row = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = :table_name
            )
            """
        ),
        {"table_name": CONFIRMED_TARGETS_TABLE},
    ).fetchone()
    return bool(row and row[0])


def upsert_confirmed_target_handles(
    conn,
    *,
    workspace_id: str,
    handles: Iterable[str],
) -> int:
    from sqlalchemy import text

    if not confirmed_targets_table_exists(conn):
        return 0

    normalized_handles = set()
    for handle in handles:
        normalized_handle = normalize_target_handle(handle)
        if not normalized_handle:
            continue
        if normalized_handle.startswith(_SEED_PLACEHOLDER_PREFIX):
            continue
        normalized_handles.add(normalized_handle)

    normalized_handles = sorted(normalized_handles)
    if not normalized_handles:
        return 0

    conn.execute(
        text(
            f"""
            INSERT INTO {CONFIRMED_TARGETS_TABLE} (
                workspace_id,
                handle,
                updated_at
            ) VALUES (
                :workspace_id,
                :handle,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (workspace_id, handle) DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        [
            {"workspace_id": workspace_id, "handle": handle}
            for handle in normalized_handles
        ],
    )
    return len(normalized_handles)


def load_confirmed_targets_total(
    conn,
    *,
    workspace_id: str,
    handle: Optional[str] = None,
) -> Optional[int]:
    from sqlalchemy import text

    if not confirmed_targets_table_exists(conn):
        return None

    query = f"""
        SELECT COUNT(*)
        FROM {CONFIRMED_TARGETS_TABLE}
        WHERE workspace_id = :workspace_id
    """
    params = {"workspace_id": workspace_id}

    normalized_handle = normalize_target_handle(handle)
    if normalized_handle:
        query += " AND handle = :handle"
        params["handle"] = normalized_handle

    row = conn.execute(text(query), params).fetchone()
    return int(row[0] or 0) if row else 0
