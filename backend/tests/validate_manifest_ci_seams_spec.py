import importlib.util
import sys
from pathlib import Path

import yaml


LOCAL_CORE_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "mindscape-ai-local-core"
)
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
for candidate in (LOCAL_CORE_ROOT, BACKEND_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)


def _load_validate_manifest_module():
    script_path = LOCAL_CORE_ROOT / "scripts" / "ci" / "validate_manifest.py"
    spec = importlib.util.spec_from_file_location("validate_manifest_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_manifest(tmp_path: Path) -> Path:
    cap_dir = tmp_path / "demo_capability"
    cap_dir.mkdir()
    manifest_path = cap_dir / "manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "code": "demo_capability",
                "display_name": "Demo Capability",
                "version": "0.1.0",
                "type": "feature",
                "portability": {
                    "min_local_core_version": "0.9.0",
                    "environments": ["local-core", "cloud"],
                    "degradation_strategy": "graceful",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_validate_manifest_script_facade_exports_core_contracts(tmp_path):
    module = _load_validate_manifest_module()

    for name in (
        "ValidationError",
        "ValidationResult",
        "validate_manifest",
        "validate_directory",
        "format_results",
        "main",
        "_validate_runtime_read_path_budgets",
    ):
        assert hasattr(module, name)

    result = module.validate_manifest(_write_manifest(tmp_path))
    assert result.valid is True
    assert result.errors == []

    formatted = module.format_results([result])
    assert "Manifest Validation Results" in formatted
    assert "[OK] demo_capability: Valid" in formatted


def test_validate_manifest_facade_keeps_runtime_budget_helper_reexport():
    module = _load_validate_manifest_module()
    errors = []
    manifest = {
        "code": "demo_capability",
        "apis": [{"prefix": "/api/v1/demo"}],
        "runtime_read_path_budgets": [
            {
                "id": "demo_list",
                "endpoint_class": "ui_list",
                "method": "GET",
                "path": "/api/v1/demo/items",
                "request_query": {"workspace_id": "{workspace_id}", "limit": 20},
                "purpose": "Demo list",
                "max_ttfb_ms": 100,
                "max_total_ms": 200,
                "max_response_bytes": 500,
                "db_read_model": "raw_table",
                "forbidden_sources": ["demo_payload.entry_json"],
                "expected_status": 200,
            }
        ],
    }

    module._validate_runtime_read_path_budgets(manifest, manifest["code"], errors)

    assert any(error.field.endswith(".db_read_model") for error in errors)
    assert any("db_read_model must be one of" in error.message for error in errors)
