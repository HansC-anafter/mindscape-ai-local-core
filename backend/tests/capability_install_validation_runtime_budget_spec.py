import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_validate_manifest_module():
    script_path = REPO_ROOT / "scripts" / "ci" / "validate_manifest.py"
    spec = importlib.util.spec_from_file_location("local_validate_manifest", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _manifest_with_runtime_budget(budget):
    return {
        "code": "demo",
        "version": "1.0.0",
        "portability": {
            "min_local_core_version": "0.9.0",
            "environments": ["local-core", "cloud"],
        },
        "apis": [
            {
                "name": "demo_api",
                "path": "api/demo.py",
                "prefix": "/api/v1/demo",
            }
        ],
        "runtime_read_path_budgets": [budget],
    }


def _runtime_budget(**overrides):
    budget = {
        "id": "demo_list",
        "endpoint_class": "ui_list",
        "method": "GET",
        "path": "/api/v1/demo/items",
        "request_query": {
            "workspace_id": "{workspace_id}",
            "limit": 20,
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


def _runtime_budget_errors(manifest):
    module = _load_validate_manifest_module()
    errors = []
    module._validate_runtime_read_path_budgets(manifest, manifest["code"], errors)
    return errors


def test_runtime_read_path_budget_semantic_validation_rejects_missing_field():
    budget = _runtime_budget()
    del budget["request_query"]
    errors = _runtime_budget_errors(_manifest_with_runtime_budget(budget))

    assert any(error.field.endswith(".request_query") for error in errors)
    assert any("Missing required budget field" in error.message for error in errors)


def test_runtime_read_path_budget_semantic_validation_rejects_duplicate_ids():
    manifest = _manifest_with_runtime_budget(_runtime_budget())
    manifest["runtime_read_path_budgets"].append(_runtime_budget())
    errors = _runtime_budget_errors(manifest)

    assert any(error.field.endswith(".id") and "unique" in error.message for error in errors)


def test_runtime_read_path_budget_requires_known_endpoint_class():
    errors = _runtime_budget_errors(
        _manifest_with_runtime_budget(_runtime_budget(endpoint_class="detail"))
    )

    assert any("endpoint_class must be one of" in error.message for error in errors)


def test_runtime_read_path_budget_requires_forbidden_sources_for_list_endpoint():
    errors = _runtime_budget_errors(
        _manifest_with_runtime_budget(_runtime_budget(forbidden_sources=[]))
    )

    assert any(
        error.field.endswith(".forbidden_sources")
        and "at least one denied source" in error.message
        for error in errors
    )


def test_runtime_read_path_budget_accepts_non_empty_forbidden_sources():
    errors = _runtime_budget_errors(_manifest_with_runtime_budget(_runtime_budget()))

    assert not [error for error in errors if ".forbidden_sources" in error.field]
