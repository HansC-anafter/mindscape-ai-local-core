import argparse
import importlib.util
import json
from pathlib import Path

import yaml


LOCAL_CORE_ROOT = Path(__file__).resolve().parents[2]


def _load_checker_module():
    script_path = (
        LOCAL_CORE_ROOT
        / "scripts"
        / "maintenance"
        / "check_runtime_read_path_budget.py"
    )
    spec = importlib.util.spec_from_file_location("check_runtime_read_path_budget", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_installed_manifest(tmp_path: Path, budgets: list[dict]) -> None:
    cap_dir = tmp_path / "backend" / "app" / "capabilities" / "demo"
    cap_dir.mkdir(parents=True)
    manifest = {
        "code": "demo",
        "version": "1.0.0",
        "apis": [
            {
                "name": "demo_api",
                "path": "api/demo.py",
                "prefix": "/api/v1/demo",
            }
        ],
        "runtime_read_path_budgets": budgets,
    }
    (cap_dir / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )


def _budget(**overrides):
    budget = {
        "id": "demo_list",
        "endpoint_class": "ui_list",
        "method": "GET",
        "path": "/api/v1/demo/items",
        "request_query": {
            "workspace_id": "{workspace_id}",
            "limit": 10,
        },
        "purpose": "Demo list",
        "max_ttfb_ms": 100,
        "max_total_ms": 200,
        "max_response_bytes": 500,
        "db_read_model": "projection",
        "forbidden_sources": ["demo_payload.entry_json"],
        "expected_status": 200,
    }
    budget.update(overrides)
    return budget


def _args(tmp_path: Path):
    return argparse.Namespace(
        capability="demo",
        workspace_id="workspace-1",
        api_base="http://backend.local",
        frontend_base="http://frontend.local",
        output=str(tmp_path / "budget-report.json"),
        warmup_count=1,
        sample_count=2,
        timeout_seconds=1.0,
        include_pg_stat_statements=False,
        local_core_root=str(tmp_path),
    )


def test_budget_checker_fails_when_response_bytes_exceed_budget(tmp_path):
    module = _load_checker_module()
    _write_installed_manifest(tmp_path, [_budget(max_response_bytes=10)])

    def fake_get(_url, _timeout):
        return {
            "status": 200,
            "ttfb_ms": 10,
            "total_ms": 20,
            "response_bytes": 100,
            "error": None,
        }

    report = module.run_budget_check(_args(tmp_path), http_get=fake_get)

    assert report["passed"] is False
    assert report["budgets"][0]["failures"][0]["field"] == "response_bytes"


def test_budget_checker_fails_when_ttfb_exceeds_budget(tmp_path):
    module = _load_checker_module()
    _write_installed_manifest(tmp_path, [_budget(max_ttfb_ms=50)])

    def fake_get(_url, _timeout):
        return {
            "status": 200,
            "ttfb_ms": 75,
            "total_ms": 90,
            "response_bytes": 100,
            "error": None,
        }

    report = module.run_budget_check(_args(tmp_path), http_get=fake_get)

    assert report["passed"] is False
    assert report["budgets"][0]["failures"][0]["field"] == "ttfb_ms"


def test_budget_checker_passes_and_writes_report_when_samples_fit_budget(tmp_path):
    module = _load_checker_module()
    _write_installed_manifest(tmp_path, [_budget()])

    observed_urls = []

    def fake_get(url, _timeout):
        observed_urls.append(url)
        return {
            "status": 200,
            "ttfb_ms": 50,
            "total_ms": 75,
            "response_bytes": 120,
            "error": None,
        }

    args = _args(tmp_path)
    report = module.run_budget_check(args, http_get=fake_get)
    written = json.loads(Path(args.output).read_text(encoding="utf-8"))

    assert report["passed"] is True
    assert written["passed"] is True
    assert len(report["budgets"][0]["samples"]) == 3
    assert report["budgets"][0]["summary"]["measured_count"] == 2
    assert observed_urls[0].startswith(
        "http://backend.local/api/v1/demo/items?workspace_id=workspace-1"
    )
