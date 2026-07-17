#!/usr/bin/env python3
"""Emit the exact live task-index catalog joined to ownership metadata."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.database.connection_factory import ConnectionFactory  # noqa: E402
from backend.app.database.task_index_manifest import (  # noqa: E402
    task_index_ownership,
)


CATALOG_SQL = text(
    """
    SELECT
      p.tablename AS relation,
      p.indexname AS index_name,
      p.indexdef AS definition,
      pg_relation_size(format('%I.%I', p.schemaname, p.indexname)::regclass)
        AS index_bytes,
      COALESCE(s.idx_scan, 0) AS idx_scan,
      COALESCE(s.idx_tup_read, 0) AS idx_tup_read,
      COALESCE(s.idx_tup_fetch, 0) AS idx_tup_fetch,
      i.indisvalid AS is_valid,
      i.indisready AS is_ready
    FROM pg_indexes p
    JOIN pg_class c
      ON c.relname = p.indexname
    JOIN pg_namespace n
      ON n.oid = c.relnamespace AND n.nspname = p.schemaname
    JOIN pg_index i
      ON i.indexrelid = c.oid
    LEFT JOIN pg_stat_user_indexes s
      ON s.schemaname = p.schemaname
     AND s.relname = p.tablename
     AND s.indexrelname = p.indexname
    WHERE p.schemaname = 'public'
      AND p.tablename IN ('tasks', 'task_summary_projection')
    ORDER BY p.tablename, p.indexname
    """
)

TABLE_STATS_SQL = text(
    """
    SELECT
      relname AS relation,
      n_tup_ins,
      n_tup_upd,
      n_tup_hot_upd,
      n_dead_tup,
      last_autovacuum,
      last_autoanalyze
    FROM pg_stat_user_tables
    WHERE relname IN ('tasks', 'task_summary_projection')
    ORDER BY relname
    """
)

STATS_RESET_SQL = text(
    """
    SELECT stats_reset
    FROM pg_stat_database
    WHERE datname = current_database()
    """
)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def build_manifest_receipt(
    rows: Iterable[Mapping[str, Any]],
    *,
    table_stats: Iterable[Mapping[str, Any]],
    captured_at: str,
    stats_reset: str | None,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    unregistered: list[str] = []
    for raw in rows:
        row = dict(raw)
        relation = str(row["relation"])
        index_name = str(row["index_name"])
        ownership = task_index_ownership(relation, index_name)
        if ownership is None:
            unregistered.append(f"{relation}.{index_name}")
            ownership_payload = {
                "relation": relation,
                "index_name": index_name,
                "owner": "unresolved",
                "query_owner": "unresolved",
                "writer_cost": "unmeasured",
                "replacement": "unresolved",
                "retirement_condition": "registration-and-owner-evidence-required",
                "status": "blocked_keep",
            }
        else:
            ownership_payload = ownership.to_dict()
        entries.append(
            {
                **ownership_payload,
                "definition": str(row["definition"]),
                "index_bytes": int(row.get("index_bytes") or 0),
                "idx_scan": int(row.get("idx_scan") or 0),
                "idx_tup_read": int(row.get("idx_tup_read") or 0),
                "idx_tup_fetch": int(row.get("idx_tup_fetch") or 0),
                "is_valid": bool(row.get("is_valid")),
                "is_ready": bool(row.get("is_ready")),
                "registered": ownership is not None,
            }
        )
    normalized_stats = []
    for raw in table_stats:
        row = dict(raw)
        normalized_stats.append(
            {
                "relation": str(row["relation"]),
                "n_tup_ins": int(row.get("n_tup_ins") or 0),
                "n_tup_upd": int(row.get("n_tup_upd") or 0),
                "n_tup_hot_upd": int(row.get("n_tup_hot_upd") or 0),
                "n_dead_tup": int(row.get("n_dead_tup") or 0),
                "last_autovacuum": _iso(row.get("last_autovacuum")),
                "last_autoanalyze": _iso(row.get("last_autoanalyze")),
            }
        )
    relation_counts = {
        relation: sum(1 for entry in entries if entry["relation"] == relation)
        for relation in ("tasks", "task_summary_projection")
    }
    pack_specific = [
        entry
        for entry in entries
        if entry["status"] == "retirement_candidate_blocked"
    ]
    invalid = [
        f"{entry['relation']}.{entry['index_name']}"
        for entry in entries
        if not entry["is_valid"] or not entry["is_ready"]
    ]
    return {
        "captured_at": captured_at,
        "stats_reset": stats_reset,
        "relation_counts": relation_counts,
        "registered_count": sum(1 for entry in entries if entry["registered"]),
        "unregistered": unregistered,
        "invalid_or_not_ready": invalid,
        "pack_specific_retirement_count": len(pack_specific),
        "table_stats": normalized_stats,
        "indexes": entries,
        "ok": not unregistered and not invalid,
    }


def collect_manifest() -> dict[str, Any]:
    factory = ConnectionFactory()
    with factory.get_connection() as conn:
        rows = conn.execute(CATALOG_SQL).mappings().all()
        table_stats = conn.execute(TABLE_STATS_SQL).mappings().all()
        stats_reset = conn.execute(STATS_RESET_SQL).scalar()
    return build_manifest_receipt(
        rows,
        table_stats=table_stats,
        captured_at=datetime.now(timezone.utc).isoformat(),
        stats_reset=_iso(stats_reset),
    )


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    payload = collect_manifest()
    if args.receipt:
        _write_atomic(args.receipt, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
