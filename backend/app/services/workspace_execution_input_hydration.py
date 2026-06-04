"""Bounded execution input hydration for compact run-log projections."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from sqlalchemy import bindparam, text


POST_DETAIL_PLAYBOOK_CODE = "ig_pin_post_detail"
POST_DETAIL_INPUT_KEYS = ("shortcode", "shortcodes", "tags", "source_handle")


def hydrate_missing_execution_inputs(conn, rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Hydrate bounded post-detail inputs when stale projections omit them."""

    row_list = [row for row in rows if _needs_post_detail_hydration(row)]
    task_ids = list(
        dict.fromkeys(
            str(row.get("task_id") or "").strip()
            for row in row_list
            if str(row.get("task_id") or "").strip()
        )
    )
    if not task_ids:
        return {}

    statement = text(
        """
        SELECT id, params, execution_context
        FROM tasks
        WHERE id IN :task_ids
          AND pack_id = :pack_id
        """
    ).bindparams(bindparam("task_ids", expanding=True))
    fetched = conn.execute(
        statement,
        {"task_ids": task_ids, "pack_id": POST_DETAIL_PLAYBOOK_CODE},
    ).fetchall()

    overlays: Dict[str, Dict[str, Any]] = {}
    for fetched_row in fetched:
        mapping = _mapping(fetched_row)
        task_id = str(mapping.get("id") or "").strip()
        if not task_id:
            continue
        overlay = _compact_post_detail_inputs(
            _as_dict(mapping.get("params")),
            _as_dict(mapping.get("execution_context")),
        )
        if overlay:
            overlays[task_id] = overlay
    return overlays


def _needs_post_detail_hydration(row: Dict[str, Any]) -> bool:
    if str(row.get("pack_id") or "") != POST_DETAIL_PLAYBOOK_CODE:
        return False
    compact_inputs = _as_dict(row.get("compact_inputs"))
    if not compact_inputs:
        return True
    has_shortcode = bool(compact_inputs.get("shortcode") or compact_inputs.get("shortcodes"))
    has_tags = bool(compact_inputs.get("tags"))
    return not (has_shortcode and has_tags)


def _compact_post_detail_inputs(
    params: Dict[str, Any],
    execution_context: Dict[str, Any],
) -> Dict[str, Any]:
    inputs = _as_dict(execution_context.get("inputs"))
    hydrated: Dict[str, Any] = {}
    for key in POST_DETAIL_INPUT_KEYS:
        value = inputs.get(key)
        if value in (None, "", [], {}):
            value = params.get(key)
        if value not in (None, "", [], {}):
            hydrated[key] = value
    return hydrated


def _mapping(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    if isinstance(row, dict):
        return row
    return dict(row)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}
