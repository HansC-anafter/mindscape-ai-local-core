#!/usr/bin/env python3
"""Check installed capability read-path budgets against live runtime endpoints."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import yaml


PG_STAT_STATEMENTS_SQL = """
SELECT calls,
       round(total_exec_time::numeric, 2) AS total_ms,
       round(mean_exec_time::numeric, 2) AS mean_ms,
       left(query, 180) AS query
FROM pg_stat_statements
WHERE query ILIKE '%ig_reference_catalog%'
   OR query ILIKE '%ig_accounts_flat%'
ORDER BY total_exec_time DESC
LIMIT 10;
""".strip()


HttpMeasurement = dict[str, Any]
HttpGetter = Callable[[str, float], HttpMeasurement]


def _resolve_default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_path(local_core_root: Path, capability: str) -> Path:
    return (
        local_core_root
        / "backend"
        / "app"
        / "capabilities"
        / capability
        / "manifest.yaml"
    )


def load_manifest(local_core_root: Path, capability: str) -> tuple[dict[str, Any], Path]:
    path = _manifest_path(local_core_root, capability)
    if not path.exists():
        raise FileNotFoundError(f"installed manifest not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle) or {}
    if not isinstance(manifest, dict):
        raise ValueError(f"installed manifest must be an object: {path}")
    return manifest, path


def _query_value_to_string(value: Any, workspace_id: str) -> str:
    if isinstance(value, str):
        return value.replace("{workspace_id}", workspace_id)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def resolve_query(request_query: dict[str, Any], workspace_id: str) -> dict[str, str]:
    return {
        key: _query_value_to_string(value, workspace_id)
        for key, value in request_query.items()
    }


def build_url(api_base: str, path: str, query: dict[str, str]) -> str:
    base = api_base.rstrip("/")
    mounted_path = path if path.startswith("/") else f"/{path}"
    encoded = urllib.parse.urlencode(query)
    if encoded:
        return f"{base}{mounted_path}?{encoded}"
    return f"{base}{mounted_path}"


def _http_get_measurement(url: str, timeout_seconds: float) -> HttpMeasurement:
    request = urllib.request.Request(url, method="GET")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            headers_received = time.perf_counter()
            body = response.read()
            completed = time.perf_counter()
            status = int(response.getcode())
    except urllib.error.HTTPError as exc:
        headers_received = time.perf_counter()
        body = exc.read()
        completed = time.perf_counter()
        status = int(exc.code)
    except Exception as exc:
        completed = time.perf_counter()
        return {
            "status": None,
            "ttfb_ms": None,
            "total_ms": round((completed - started) * 1000, 3),
            "response_bytes": 0,
            "error": str(exc),
        }

    return {
        "status": status,
        "ttfb_ms": round((headers_received - started) * 1000, 3),
        "total_ms": round((completed - started) * 1000, 3),
        "response_bytes": len(body),
        "error": None,
    }


def _percentile_like(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def _summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [sample for sample in samples if sample.get("phase") == "measured"]
    summary: dict[str, Any] = {"measured_count": len(measured)}
    for key in ("ttfb_ms", "total_ms", "response_bytes"):
        values = [
            sample[key]
            for sample in measured
            if isinstance(sample.get(key), (int, float))
        ]
        if not values:
            summary[key] = {"max": None, "median": None, "p95_like": None}
            continue
        summary[key] = {
            "max": max(values),
            "median": round(statistics.median(values), 3),
            "p95_like": _percentile_like(values, 0.95),
        }
    return summary


def _evaluate_sample(
    budget: dict[str, Any],
    sample: dict[str, Any],
) -> list[dict[str, Any]]:
    failures = []
    expected_status = budget.get("expected_status", 200)
    status = sample.get("status")
    if status != expected_status:
        failures.append(
            {
                "field": "status",
                "expected": expected_status,
                "actual": status,
                "error": sample.get("error"),
            }
        )
        return failures

    for metric, budget_field in (
        ("ttfb_ms", "max_ttfb_ms"),
        ("total_ms", "max_total_ms"),
        ("response_bytes", "max_response_bytes"),
    ):
        actual = sample.get(metric)
        maximum = budget.get(budget_field)
        if not isinstance(actual, (int, float)) or actual > maximum:
            failures.append(
                {
                    "field": metric,
                    "budget": maximum,
                    "actual": actual,
                }
            )
    return failures


def _collect_pg_stat_snapshot(timeout_seconds: float = 10.0) -> dict[str, Any]:
    database_url = os.environ.get("DATABASE_URL")
    command = ["psql"]
    if database_url:
        command.append(database_url)
    command.extend(["-c", PG_STAT_STATEMENTS_SQL])
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "sql": PG_STAT_STATEMENTS_SQL,
        }
    return {
        "available": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "sql": PG_STAT_STATEMENTS_SQL,
    }


def run_budget_check(
    args: argparse.Namespace,
    *,
    http_get: HttpGetter | None = None,
    pg_stat_provider: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    http_getter = http_get or _http_get_measurement
    local_core_root = Path(args.local_core_root).resolve()
    manifest, manifest_path = load_manifest(local_core_root, args.capability)
    budgets = manifest.get("runtime_read_path_budgets")
    if not isinstance(budgets, list) or not budgets:
        raise ValueError(
            f"installed manifest has no runtime_read_path_budgets: {manifest_path}"
        )

    report: dict[str, Any] = {
        "capability": args.capability,
        "manifest_path": str(manifest_path),
        "api_base": args.api_base,
        "frontend_base": args.frontend_base,
        "workspace_id": args.workspace_id,
        "warmup_count": args.warmup_count,
        "sample_count": args.sample_count,
        "passed": True,
        "budgets": [],
    }

    for budget in budgets:
        request_query = resolve_query(budget["request_query"], args.workspace_id)
        url = build_url(args.api_base, budget["path"], request_query)
        budget_result = {
            "id": budget.get("id"),
            "endpoint_class": budget.get("endpoint_class"),
            "method": budget.get("method"),
            "path": budget.get("path"),
            "url": url,
            "request_query": request_query,
            "limits": {
                "max_ttfb_ms": budget.get("max_ttfb_ms"),
                "max_total_ms": budget.get("max_total_ms"),
                "max_response_bytes": budget.get("max_response_bytes"),
            },
            "samples": [],
            "failures": [],
        }

        total_samples = args.warmup_count + args.sample_count
        for sample_index in range(total_samples):
            phase = "warmup" if sample_index < args.warmup_count else "measured"
            measurement = http_getter(url, args.timeout_seconds)
            sample = {
                "index": sample_index,
                "phase": phase,
                **measurement,
            }
            budget_result["samples"].append(sample)
            if phase != "measured":
                continue
            failures = _evaluate_sample(budget, sample)
            for failure in failures:
                failure["sample_index"] = sample_index
                budget_result["failures"].append(failure)

        budget_result["summary"] = _summarize_samples(budget_result["samples"])
        if budget_result["failures"]:
            report["passed"] = False
        report["budgets"].append(budget_result)

    if args.include_pg_stat_statements:
        provider = pg_stat_provider or _collect_pg_stat_snapshot
        report["pg_stat_statements"] = provider()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check installed capability runtime read-path budgets."
    )
    parser.add_argument("--capability", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--frontend-base", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--warmup-count", type=int, default=1)
    parser.add_argument("--sample-count", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--include-pg-stat-statements", action="store_true")
    parser.add_argument(
        "--local-core-root",
        default=str(_resolve_default_root()),
        help="Local-core root containing backend/app/capabilities.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.warmup_count < 0:
        parser.error("--warmup-count must be >= 0")
    if args.sample_count <= 0:
        parser.error("--sample-count must be > 0")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be > 0")

    try:
        report = run_budget_check(args)
    except Exception as exc:
        print(f"runtime read-path budget check failed: {exc}", file=sys.stderr)
        return 2

    if report["passed"]:
        print(f"runtime read-path budget check passed: {args.output}")
        return 0
    print(f"runtime read-path budget check failed: {args.output}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
