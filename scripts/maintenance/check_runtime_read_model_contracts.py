#!/usr/bin/env python3
"""Check installed capability read-model contracts against runtime metadata."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

LOCAL_CORE_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
for candidate in (LOCAL_CORE_ROOT, BACKEND_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from app.services.read_models.contracts import validate_manifest_read_models
from app.services.read_models.index_verifier import (
    explain_references_forbidden_source,
    relation_columns,
    relation_exists,
)
from app.services.read_models.manifest_loader import load_installed_manifest


def _default_database_url() -> str:
    return (
        os.getenv("DATABASE_URL_CORE")
        or os.getenv("DATABASE_URL")
        or "postgresql://mindscape:mindscape_password@localhost:5432/mindscape_core"
    )


def _field_columns(read_model: dict[str, Any]) -> set[str]:
    return {
        field["column"]
        for field in read_model.get("fields", [])
        if isinstance(field, dict) and isinstance(field.get("column"), str)
    }


def _representative_sql(read_model: dict[str, Any]) -> str:
    filters = read_model.get("filters") or []
    sorts = read_model.get("sorts") or []
    where_parts: list[str] = []
    for filter_spec in filters:
        if not isinstance(filter_spec, dict):
            continue
        if filter_spec.get("required") is not True:
            continue
        field_id = filter_spec.get("field")
        column = next(
            (
                field.get("column")
                for field in read_model.get("fields", [])
                if isinstance(field, dict) and field.get("id") == field_id
            ),
            None,
        )
        if isinstance(column, str):
            where_parts.append(f"{column} IS NOT NULL")
    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    order_sql = ""
    if sorts:
        first_sort = sorts[0]
        order_parts = []
        for sort_field in first_sort.get("fields", []):
            if not isinstance(sort_field, dict):
                continue
            field_id = sort_field.get("field")
            column = next(
                (
                    field.get("column")
                    for field in read_model.get("fields", [])
                    if isinstance(field, dict) and field.get("id") == field_id
                ),
                None,
            )
            if isinstance(column, str):
                direction = str(sort_field.get("direction", "asc")).upper()
                nulls = sort_field.get("nulls")
                nulls_sql = f" NULLS {str(nulls).upper()}" if nulls else ""
                order_parts.append(f"{column} {direction}{nulls_sql}")
        if order_parts:
            order_sql = f" ORDER BY {', '.join(order_parts)}"
    return f"EXPLAIN SELECT 1 FROM {read_model['table']}{where_sql}{order_sql} LIMIT 1"


def _count_sql(count_model: dict[str, Any]) -> str:
    measures = count_model.get("measures") or []
    measure = measures[0] if measures else "1"
    return f"EXPLAIN SELECT {measure} FROM {count_model['table']} LIMIT 1"


def run_check(args: argparse.Namespace) -> dict[str, Any]:
    local_core_root = Path(args.local_core_root).resolve()
    manifest, manifest_path = load_installed_manifest(local_core_root, args.capability)
    semantic_errors = validate_manifest_read_models(manifest)
    report: dict[str, Any] = {
        "capability": args.capability,
        "manifest_path": str(manifest_path),
        "status": "pending",
        "passed": False,
        "semantic_errors": semantic_errors,
        "read_models": [],
        "count_models": [],
    }
    read_models = manifest.get("read_models") or []
    count_models = manifest.get("count_models") or []
    if not read_models:
        report["status"] = "no_read_models_declared"
        report["passed"] = not semantic_errors
        return report
    if semantic_errors:
        report["status"] = "semantic_validation_failed"
        return report
    if args.dry_run:
        report["status"] = "dry_run_valid"
        report["passed"] = True
        return report

    engine = create_engine(args.database_url)
    with engine.connect() as conn:
        for read_model in read_models:
            item = {"id": read_model["id"], "checks": [], "passed": True}
            if not relation_exists(conn, read_model["table"]):
                item["checks"].append({"name": "relation_exists", "passed": False})
                item["passed"] = False
            else:
                columns = relation_columns(conn, read_model["table"])
                missing_columns = sorted(_field_columns(read_model) - columns)
                item["checks"].append(
                    {
                        "name": "columns_exist",
                        "passed": not missing_columns,
                        "missing_columns": missing_columns,
                    }
                )
                if missing_columns:
                    item["passed"] = False
                explain_rows = conn.execute(text(_representative_sql(read_model))).fetchall()
                explain_text = "\n".join(str(row[0]) for row in explain_rows)
                forbidden_sources = [
                    source
                    for budget in manifest.get("runtime_read_path_budgets", [])
                    if isinstance(budget, dict)
                    and budget.get("read_model_id") == read_model["id"]
                    for source in budget.get("forbidden_sources", [])
                    if isinstance(source, dict)
                ]
                forbidden_hit = explain_references_forbidden_source(
                    explain_text,
                    forbidden_sources,
                )
                item["checks"].append(
                    {
                        "name": "representative_explain_forbidden_sources",
                        "passed": not forbidden_hit,
                    }
                )
                if forbidden_hit:
                    item["passed"] = False
            report["read_models"].append(item)

        for count_model in count_models:
            item = {"id": count_model["id"], "checks": [], "passed": True}
            if not relation_exists(conn, count_model["table"]):
                item["checks"].append({"name": "relation_exists", "passed": False})
                item["passed"] = False
            else:
                explain_rows = conn.execute(text(_count_sql(count_model))).fetchall()
                explain_text = "\n".join(str(row[0]) for row in explain_rows)
                forbidden_sources = [
                    source
                    for budget in manifest.get("runtime_read_path_budgets", [])
                    if isinstance(budget, dict)
                    and budget.get("count_model_id") == count_model["id"]
                    for source in budget.get("forbidden_sources", [])
                    if isinstance(source, dict)
                ]
                forbidden_hit = explain_references_forbidden_source(
                    explain_text,
                    forbidden_sources,
                )
                item["checks"].append(
                    {
                        "name": "representative_count_explain_forbidden_sources",
                        "passed": not forbidden_hit,
                    }
                )
                if forbidden_hit:
                    item["passed"] = False
            report["count_models"].append(item)
    report["passed"] = all(item["passed"] for item in report["read_models"]) and all(
        item["passed"] for item in report["count_models"]
    )
    report["status"] = "passed" if report["passed"] else "failed"
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capability", required=True)
    parser.add_argument("--local-core-root", default=str(LOCAL_CORE_ROOT))
    parser.add_argument("--database-url", default=_default_database_url())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report = run_check(args)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
