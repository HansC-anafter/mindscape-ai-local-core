#!/usr/bin/env python3
"""Land legacy task workflow results before compacting hot task context.

Old workflow runs stored full result payloads directly in
``tasks.execution_context.workflow_result``. Current runtime code compacts that
field and lands the full result separately, but historical rows can still leave
large TOAST payloads in the hot ``tasks`` table. This script performs the same
separation for legacy rows without changing their task status or completed_at.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional

from sqlalchemy import bindparam, text

from app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
from backend.app.database.connection_factory import ConnectionFactory
from backend.app.services.playbook_run_executor_core.result_compaction import (
    compact_workflow_result_for_task_context,
)


DEFAULT_PACK_IDS = (
    "ig_analyze_pinned_reference",
    "ig_analyze_following",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_loads(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        decoded = json.loads(value)
        return dict(decoded) if isinstance(decoded, dict) else {}
    return {}


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _log(args: argparse.Namespace, message: str) -> None:
    if not args.quiet:
        print(message)


def _result_summary(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("output", "summary", "message", "status"):
            raw = result.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()[:2000]
        outputs = result.get("outputs")
        if isinstance(outputs, dict):
            for key in ("summary", "message", "status"):
                raw = outputs.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()[:2000]
    return "Legacy workflow result landed for task context compaction."


def _fetch_workspace_storage(conn, workspace_id: str) -> Optional[Mapping[str, str]]:
    row = (
        conn.execute(
            text(
                """
                SELECT id, storage_base_path, artifacts_dir
                FROM workspaces
                WHERE id = :workspace_id
                """
            ),
            {"workspace_id": workspace_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    storage_base_path = str(row.get("storage_base_path") or "").strip()
    if not storage_base_path:
        return None
    return {
        "workspace_id": str(row["id"]),
        "storage_base_path": storage_base_path,
        "artifacts_dir": str(row.get("artifacts_dir") or "artifacts").strip()
        or "artifacts",
    }


def _fetch_candidates(
    conn,
    *,
    workspace_id: Optional[str],
    pack_ids: Iterable[str],
    task_ids: Iterable[str],
    batch_size: int,
    cursor_created_at: Optional[Any],
    cursor_id: Optional[str],
):
    task_id_values = tuple(str(task_id).strip() for task_id in task_ids if str(task_id).strip())
    task_id_filter = "AND id IN :task_ids" if task_id_values else ""
    stmt = (
        text(
            f"""
            SELECT
                id,
                workspace_id,
                execution_id,
                project_id,
                pack_id,
                status,
                created_at,
                completed_at,
                pg_column_size(execution_context) AS context_bytes,
                execution_context
            FROM tasks
            WHERE status IN ('succeeded', 'failed')
              AND execution_context IS NOT NULL
              AND pack_id IN :pack_ids
              AND (:workspace_id IS NULL OR workspace_id = :workspace_id)
              {task_id_filter}
              AND (
                    :cursor_created_at IS NULL
                    OR created_at > :cursor_created_at
                    OR (created_at = :cursor_created_at AND id > :cursor_id)
                  )
            ORDER BY created_at, id
            LIMIT :batch_size
            """
        )
        .bindparams(bindparam("pack_ids", expanding=True))
    )
    if task_id_values:
        stmt = stmt.bindparams(bindparam("task_ids", expanding=True))
    return list(
        conn.execute(
            stmt,
            {
                "workspace_id": workspace_id,
                "pack_ids": tuple(pack_ids),
                "task_ids": task_id_values,
                "batch_size": batch_size,
                "cursor_created_at": cursor_created_at,
                "cursor_id": cursor_id,
            },
        )
        .mappings()
        .all()
    )


def _append_backup_jsonl(
    backup_path: Optional[str],
    *,
    row: Mapping[str, Any],
    context: Dict[str, Any],
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
        "original_context_bytes": int(row.get("context_bytes") or _json_size(context)),
        "execution_context": context,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str))
        handle.write("\n")


def _write_landed_result(
    *,
    storage_base_path: str,
    artifacts_dir: str,
    execution_id: str,
    result_data: Dict[str, Any],
) -> pathlib.Path:
    artifact_dir = (
        pathlib.Path(storage_base_path).expanduser().resolve()
        / artifacts_dir
        / execution_id
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_json_path = artifact_dir / "result.json"
    with result_json_path.open("w", encoding="utf-8") as handle:
        json.dump(result_data, handle, ensure_ascii=False, indent=2, default=str)
    summary_path = artifact_dir / "summary.md"
    if not summary_path.exists():
        summary_path.write_text(_result_summary(result_data), encoding="utf-8")
    return artifact_dir


def _ensure_artifact(
    artifacts_store: PostgresArtifactsStore,
    *,
    workspace_id: str,
    task_id: str,
    execution_id: str,
    project_id: Optional[str],
    pack_id: str,
    storage_ref: str,
    result_data: Dict[str, Any],
) -> str:
    existing = artifacts_store.get_by_execution_id(execution_id)
    metadata = {
        "project_id": project_id,
        "playbook_code": pack_id,
        "legacy_task_context_compaction": True,
        "landing_result_json_path": str(pathlib.Path(storage_ref) / "result.json"),
        "landed_at": _utc_now_iso(),
    }
    if existing:
        artifacts_store.update_artifact(
            existing.id,
            storage_ref=storage_ref,
            summary=_result_summary(result_data),
            metadata={**(getattr(existing, "metadata", None) or {}), **metadata},
        )
        return existing.id

    artifact_id = str(uuid.uuid4())
    artifact = Artifact(
        id=artifact_id,
        workspace_id=workspace_id,
        task_id=task_id,
        execution_id=execution_id,
        thread_id=None,
        playbook_code=pack_id or "legacy_workflow_result",
        artifact_type=ArtifactType.DATA,
        title=f"Task Result: {execution_id[:8]}",
        summary=_result_summary(result_data),
        content={
            "_compacted": True,
            "result_json_path": str(pathlib.Path(storage_ref) / "result.json"),
        },
        storage_ref=storage_ref,
        primary_action_type=PrimaryActionType.DOWNLOAD,
        metadata=metadata,
    )
    artifacts_store.create_artifact(artifact)
    return artifact_id


def _update_task_context(conn, *, task_id: str, context: Dict[str, Any]) -> None:
    conn.execute(
        text(
            """
            UPDATE tasks
            SET execution_context = CAST(:execution_context AS JSON)
            WHERE id = :task_id
            """
        ),
        {
            "task_id": task_id,
            "execution_context": json.dumps(context, ensure_ascii=False, default=str),
        },
    )


def compact_batch(args: argparse.Namespace) -> int:
    factory = ConnectionFactory()
    artifacts_store = PostgresArtifactsStore()
    processed = 0
    inspected = 0
    cursor_created_at = None
    cursor_id = ""

    while args.limit <= 0 or processed < args.limit:
        with factory.get_connection() as conn:
            rows = _fetch_candidates(
                conn,
                workspace_id=args.workspace_id,
                pack_ids=args.pack_id,
                task_ids=args.task_id,
                batch_size=args.batch_size,
                cursor_created_at=cursor_created_at,
                cursor_id=cursor_id,
            )
        if not rows:
            break

        for row in rows:
            if 0 < args.limit <= processed:
                break
            inspected += 1
            cursor_created_at = row.get("created_at")
            cursor_id = str(row.get("id") or "")
            context = _json_loads(row.get("execution_context"))
            workflow_result = context.get("workflow_result")
            if not isinstance(workflow_result, dict):
                continue
            if bool(workflow_result.get("_compacted")):
                continue
            context_bytes = int(row.get("context_bytes") or _json_size(context))
            if context_bytes < args.min_bytes:
                continue
            compacted_probe = compact_workflow_result_for_task_context(workflow_result)
            if compacted_probe == workflow_result:
                continue

            workspace_id = str(row.get("workspace_id") or "")
            execution_id = str(row.get("execution_id") or row.get("id") or "")
            if not workspace_id or not execution_id:
                continue

            with factory.get_connection() as conn:
                storage = _fetch_workspace_storage(conn, workspace_id)
            if not storage:
                _log(
                    args,
                    f"skip task={row['id']} reason=missing_workspace_storage "
                    f"workspace={workspace_id}",
                )
                continue

            compacted_result = compact_workflow_result_for_task_context(workflow_result)
            next_context = dict(context)
            next_context["workflow_result"] = compacted_result
            next_context["workflow_result_landing"] = {
                "location": "artifact_result_json",
                "compacted_at": _utc_now_iso(),
                "original_context_bytes": context_bytes,
            }

            if not args.apply:
                _log(
                    args,
                    f"dry-run task={row['id']} pack={row.get('pack_id')} "
                    f"context_bytes={context_bytes} compact_bytes={_json_size(next_context)}",
                )
                processed += 1
                continue

            _append_backup_jsonl(
                args.backup_jsonl,
                row=row,
                context=context,
            )
            artifact_dir = _write_landed_result(
                storage_base_path=storage["storage_base_path"],
                artifacts_dir=storage["artifacts_dir"],
                execution_id=execution_id,
                result_data=workflow_result,
            )
            artifact_id = _ensure_artifact(
                artifacts_store,
                workspace_id=workspace_id,
                task_id=str(row["id"]),
                execution_id=execution_id,
                project_id=row.get("project_id"),
                pack_id=str(row.get("pack_id") or ""),
                storage_ref=str(artifact_dir),
                result_data=workflow_result,
            )
            next_context["workflow_result_landing"]["artifact_id"] = artifact_id
            next_context["workflow_result_landing"]["result_json_path"] = str(
                artifact_dir / "result.json"
            )
            with factory.get_connection() as conn:
                _update_task_context(conn, task_id=str(row["id"]), context=next_context)
                conn.commit()
            processed += 1
            _log(
                args,
                f"compacted task={row['id']} pack={row.get('pack_id')} "
                f"context_bytes={context_bytes} compact_bytes={_json_size(next_context)} "
                f"artifact_id={artifact_id}",
            )

    print(f"summary inspected={inspected} processed={processed} apply={args.apply}")
    return processed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Land and compact legacy task workflow_result contexts."
    )
    parser.add_argument("--workspace-id", default=None)
    parser.add_argument("--pack-id", action="append", default=list(DEFAULT_PACK_IDS))
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--backup-jsonl", default=None)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--min-bytes", type=int, default=256 * 1024)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    compact_batch(args)


if __name__ == "__main__":
    main()
