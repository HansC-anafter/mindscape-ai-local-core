#!/usr/bin/env python3
"""Compact task payload fields that exceed the configured hot-row budget."""

from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import bindparam, text

from backend.app.database.connection_factory import ConnectionFactory
from backend.app.services.task_payload_budget import (
    DEFAULT_TASK_PAYLOAD_LIMITS,
    apply_task_payload_budget,
    json_payload_size,
)


FIELDS = ("params", "result", "execution_context", "blocked_payload")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_loads(value: Any) -> Any:
    if isinstance(value, str) and value.strip():
        return json.loads(value)
    return value


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _payload_size(value: Any) -> int:
    return json_payload_size(value)


def _append_backup_jsonl(
    backup_path: str | None,
    *,
    row: Mapping[str, Any],
) -> None:
    if not backup_path:
        return
    path = pathlib.Path(backup_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "created_at": _utc_now_iso(),
        "task_id": str(row.get("id") or ""),
        "workspace_id": str(row.get("workspace_id") or ""),
        "execution_id": str(row.get("execution_id") or ""),
        "pack_id": str(row.get("pack_id") or ""),
        "task_created_at": str(row.get("created_at") or ""),
        "payloads": {field: row.get(field) for field in FIELDS},
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_json_dumps(record))
        handle.write("\n")


def _fetch_candidates(
    conn,
    *,
    task_ids: list[str],
    recent_hours: int,
    limit: int,
) -> list[dict[str, Any]]:
    task_id_values = tuple(task_id for task_id in task_ids if task_id)
    task_filter = "id IN :task_ids" if task_id_values else (
        "created_at >= now() - (:recent_hours * interval '1 hour')"
    )
    stmt = text(
        f"""
        SELECT
            id,
            workspace_id,
            execution_id,
            pack_id,
            created_at,
            params,
            result,
            execution_context,
            blocked_payload,
            octet_length(coalesce(params::text, '')) AS params_db_bytes,
            octet_length(coalesce(result::text, '')) AS result_db_bytes,
            octet_length(coalesce(execution_context::text, ''))
                AS execution_context_db_bytes,
            octet_length(coalesce(blocked_payload::text, ''))
                AS blocked_payload_db_bytes
        FROM tasks
        WHERE {task_filter}
          AND (
                octet_length(coalesce(params::text, '')) > :params_budget
             OR octet_length(coalesce(result::text, '')) > :result_budget
             OR octet_length(coalesce(execution_context::text, ''))
                    > :execution_context_budget
             OR octet_length(coalesce(blocked_payload::text, ''))
                    > :blocked_payload_budget
          )
        ORDER BY created_at, id
        LIMIT :limit
        """
    )
    if task_id_values:
        stmt = stmt.bindparams(bindparam("task_ids", expanding=True))
    rows = conn.execute(
        stmt,
        {
            "task_ids": task_id_values,
            "recent_hours": recent_hours,
            "limit": limit,
            "params_budget": DEFAULT_TASK_PAYLOAD_LIMITS["params"],
            "result_budget": DEFAULT_TASK_PAYLOAD_LIMITS["result"],
            "execution_context_budget": DEFAULT_TASK_PAYLOAD_LIMITS[
                "execution_context"
            ],
            "blocked_payload_budget": DEFAULT_TASK_PAYLOAD_LIMITS["blocked_payload"],
        },
    ).mappings()
    return [dict(row) for row in rows]


def _compact_row(row: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    updates: dict[str, Any] = {}
    sizes: dict[str, int] = {}
    for field in FIELDS:
        raw_value = _json_loads(row.get(field))
        before_size = _payload_size(raw_value)
        db_before_size = int(row.get(f"{field}_db_bytes") or before_size)
        budget = DEFAULT_TASK_PAYLOAD_LIMITS[field]
        if before_size <= budget and db_before_size <= budget:
            sizes[f"{field}_db_before"] = db_before_size
            sizes[f"{field}_before"] = before_size
            sizes[f"{field}_after"] = before_size
            continue
        if before_size <= budget:
            next_value = raw_value
        else:
            next_value = apply_task_payload_budget(
                field,
                raw_value,
                limit_bytes=budget,
            )
        after_size = _payload_size(next_value)
        sizes[f"{field}_db_before"] = db_before_size
        sizes[f"{field}_before"] = before_size
        sizes[f"{field}_after"] = after_size
        if after_size <= budget and (next_value != raw_value or db_before_size > budget):
            updates[field] = next_value
    return updates, sizes


def _apply_updates(conn, *, task_id: str, updates: Mapping[str, Any]) -> None:
    assignments = ", ".join(
        f"{field} = CAST(:{field} AS JSON)" for field in updates.keys()
    )
    params = {"task_id": task_id}
    params.update({field: _json_dumps(value) for field, value in updates.items()})
    conn.execute(
        text(
            f"""
            UPDATE tasks
            SET {assignments}
            WHERE id = :task_id
            """
        ),
        params,
    )


def run(args: argparse.Namespace) -> int:
    factory = ConnectionFactory()
    with factory.get_connection() as conn:
        rows = _fetch_candidates(
            conn,
            task_ids=args.task_id,
            recent_hours=args.recent_hours,
            limit=args.limit,
        )

    processed = 0
    for row in rows:
        updates, sizes = _compact_row(row)
        if not updates:
            print(
                f"skip task={row['id']} reason=no_safe_compaction sizes="
                f"{_json_dumps(sizes)}"
            )
            continue
        if not args.apply:
            print(
                f"dry-run task={row['id']} fields={','.join(updates.keys())} "
                f"sizes={_json_dumps(sizes)}"
            )
            processed += 1
            continue
        _append_backup_jsonl(args.backup_jsonl, row=row)
        with factory.get_connection() as conn:
            _apply_updates(conn, task_id=str(row["id"]), updates=updates)
            conn.commit()
        print(
            f"compacted task={row['id']} fields={','.join(updates.keys())} "
            f"sizes={_json_dumps(sizes)}"
        )
        processed += 1

    print(f"summary candidates={len(rows)} processed={processed} apply={args.apply}")
    return processed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compact task payload fields that exceed hot-row budgets."
    )
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--recent-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--backup-jsonl", default=None)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
