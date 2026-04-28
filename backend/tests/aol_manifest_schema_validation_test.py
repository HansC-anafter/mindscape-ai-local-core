import importlib.util
import sys
from pathlib import Path

import yaml


LOCAL_CORE_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "mindscape-ai-local-core"
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


def _write_manifest(tmp_path: Path, manifest: dict) -> Path:
    cap_dir = tmp_path / manifest["code"]
    cap_dir.mkdir()
    manifest_path = cap_dir / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


def _base_manifest() -> dict:
    return {
        "code": "demo_capability",
        "display_name": "Demo Capability",
        "version": "0.1.0",
        "type": "feature",
        "portability": {
            "min_local_core_version": "0.9.0",
            "environments": ["local-core", "cloud"],
            "degradation_strategy": "graceful",
        },
    }


def test_validate_manifest_accepts_aol2_contract_fields(tmp_path):
    manifest = {
        **_base_manifest(),
        "aol_maturity": "AOL-2",
        "object_exports": [
            {
                "kind": "reference",
                "display_name": "Reference",
                "canonical_schema": "capabilities.demo_capability.schema.reference",
                "id_field": "reference_id",
                "summary_fields": ["title", "summary"],
                "supports": ["summary", "detail", "actions"],
                "granularity": "object_root",
                "selector_families": ["object_root", "image_region"],
                "indexer_backend": "capabilities.demo_capability.services.aol:sync_reference_index",
                "mention_fields": ["title", "summary"],
                "owner_surface_patterns": ["/references/{reference_id}"],
            }
        ],
        "affordances": [
            {
                "verb": "use_as_reference",
                "object_kinds": ["reference"],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "required_roles": ["source", "target"],
                "write_modes": ["proposal_only"],
                "planner_backend": "capabilities.demo_capability.services.aol:plan_reference_use",
                "executor_backend": "capabilities.demo_capability.services.aol:execute_reference_use",
            }
        ],
    }
    result = _load_validate_manifest_module().validate_manifest(_write_manifest(tmp_path, manifest))

    assert result.valid is True
    assert result.errors == []


def test_validate_manifest_rejects_incomplete_aol2_claim(tmp_path):
    manifest = {
        **_base_manifest(),
        "aol_maturity": "AOL-2",
        "object_exports": [
            {
                "kind": "reference",
                "display_name": "Reference",
                "id_field": "reference_id",
            }
        ],
    }
    result = _load_validate_manifest_module().validate_manifest(_write_manifest(tmp_path, manifest))
    messages = [error.message for error in result.errors]

    assert result.valid is False
    assert any("selector_families" in message for message in messages)
    assert any("indexer_backend" in message for message in messages)
    assert any("mention_fields" in message for message in messages)
    assert any("affordance" in message for message in messages)


def test_local_and_cloud_manifest_schemas_expose_aol_contract_fields():
    cloud_schema_path = (
        LOCAL_CORE_ROOT.parent
        / "mindscape-ai-cloud"
        / "capabilities"
        / "manifest.schema.yaml"
    )
    assert cloud_schema_path.exists()

    local_schema = yaml.safe_load((LOCAL_CORE_ROOT / "schemas" / "manifest.schema.yaml").read_text())
    cloud_schema = yaml.safe_load(cloud_schema_path.read_text())
    for field in ("selector_families", "indexer_backend", "mention_fields"):
        assert field in local_schema["properties"]["object_exports"]["items"]["properties"]
        assert field in cloud_schema["properties"]["object_exports"]["items"]["properties"]
    assert "affordances" in local_schema["properties"]
    assert "affordances" in cloud_schema["properties"]
