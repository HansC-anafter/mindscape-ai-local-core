import importlib.util
import json
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

from backend.app.services.install_result import InstallResult
from backend.app.services.post_install_modules.dependency_checker import DependencyChecker
from backend.app.services.validation_service import ValidationService


def _load_validate_manifest_module():
    script_path = LOCAL_CORE_ROOT / "scripts" / "ci" / "validate_manifest.py"
    spec = importlib.util.spec_from_file_location("validate_manifest_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validate_manifest_accepts_contract_manifest_fields(tmp_path):
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
                "description": "Compatibility regression test",
                "portability": {
                    "min_local_core_version": "0.9.0",
                    "environments": ["local-core", "cloud"],
                    "degradation_strategy": "graceful",
                },
                "dependencies": {
                    "required": [],
                    "optional": [
                        {
                            "code": "ig",
                            "fallback": None,
                            "degraded_features": ["reference_import"],
                        }
                    ],
                },
                "pack_dependencies": {
                    "required": ["layer_asset_forge"],
                    "optional": ["creative_pipeline_contracts"],
                },
                "contract_exports": [
                    {
                        "contract_id": "demo_contract",
                        "module": "capabilities.demo_capability.schema.demo_contract",
                        "version": "1.0.0",
                        "legacy_aliases": ["shared.schemas.demo_contract"],
                    }
                ],
                "contract_imports": [
                    {
                        "contract_id": "visual_signal",
                        "provider_pack": "layer_asset_forge",
                        "version_range": "^1.0",
                    }
                ],
                "apis": [
                    {
                        "name": "demo_api",
                        "path": "api/__init__.py",
                        "prefix": "/api/v1/capabilities/demo_capability",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    validate_manifest = _load_validate_manifest_module().validate_manifest
    result = validate_manifest(manifest_path)

    assert result.valid is True
    assert result.errors == []


def test_validation_service_manifest_schema_accepts_contract_fields():
    service = ValidationService(LOCAL_CORE_ROOT)
    ok, errors = service._validate_manifest_schema(
        {
            "code": "demo_capability",
            "display_name": "Demo Capability",
            "version": "0.1.0",
            "portability": {
                "min_local_core_version": "0.9.0",
                "environments": ["local-core", "cloud"],
            },
            "pack_dependencies": {"required": ["layer_asset_forge"]},
            "contract_exports": [],
            "contract_imports": [],
            "playbooks": [{"code": "demo_playbook"}],
        }
    )

    assert ok is True
    assert errors == []


def test_validation_service_prefers_pack_dependencies_over_python_dependencies():
    service = ValidationService(LOCAL_CORE_ROOT)

    ok, errors, warnings = service._check_conflicts(
        {
            "code": "demo_capability",
            "dependencies": {"required": ["json"]},
            "pack_dependencies": {"required": ["layer_asset_forge"]},
        },
        installed_packs=[],
    )

    assert ok is True
    assert errors == []
    assert warnings == ["Missing dependency: layer_asset_forge"]


def test_dependency_checker_tracks_pack_dependencies_and_contract_imports(tmp_path):
    capabilities_dir = tmp_path / "backend" / "app" / "capabilities"
    capabilities_dir.mkdir(parents=True)
    (capabilities_dir / "storage").mkdir()
    (capabilities_dir / "layer_asset_forge").mkdir()

    runtime_contracts_dir = tmp_path / "data" / "runtime_contracts"
    runtime_contracts_dir.mkdir(parents=True)
    (runtime_contracts_dir / "registry.json").write_text(
        json.dumps(
            {
                "version": 1,
                "contracts": [
                    {
                        "provider_pack": "layer_asset_forge",
                        "contract_id": "visual_signal",
                        "module": "capabilities.layer_asset_forge.schema.visual_signal",
                        "version": "1.2.0",
                        "legacy_aliases": ["shared.schemas.visual_signal"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    checker = DependencyChecker(
        local_core_root=tmp_path,
        capabilities_dir=capabilities_dir,
    )
    result = InstallResult(capability_code="demo_capability")
    manifest = {
        "dependencies": {
            "required": ["json", "missing.module"],
            "optional": [
                {
                    "code": "mind_lens",
                    "name": "mind_lens",
                    "degraded_features": ["legacy_optional_pack_lane"],
                },
                {
                    "name": "missing.optional",
                    "degraded_features": ["optional_python_lane"],
                }
            ],
        },
        "pack_dependencies": {
            "required": ["storage", "missing_pack"],
            "optional": ["mind_lens"],
        },
        "contract_imports": [
            {
                "contract_id": "visual_signal",
                "provider_pack": "layer_asset_forge",
                "version_range": "^1.0",
            },
            {
                "contract_id": "storyboard",
                "provider_pack": "creative_pipeline_contracts",
                "version_range": "^1.0",
            },
        ],
    }

    missing_required, missing_optional, missing_external, missing_system_tools, degraded = (
        checker.check_dependencies(manifest, result)
    )

    assert missing_required == [
        "missing.module",
        "missing_pack",
        "storyboard@creative_pipeline_contracts (^1.0)",
    ]
    assert missing_optional == ["missing.optional", "mind_lens"]
    assert missing_external == []
    assert missing_system_tools == []
    assert degraded == {
        "mind_lens": ["legacy_optional_pack_lane"],
        "missing.optional": ["optional_python_lane"],
    }
    assert result.missing_dependencies["required"] == missing_required
    assert result.missing_dependencies["optional"] == missing_optional
    assert result.missing_dependencies["python_required"] == ["missing.module"]
    assert result.missing_dependencies["python_optional"] == ["missing.optional"]
    assert result.missing_dependencies["pack_dependencies_required"] == ["missing_pack"]
    assert result.missing_dependencies["pack_dependencies_optional"] == ["mind_lens"]
    assert result.missing_dependencies["contract_imports"] == [
        "storyboard@creative_pipeline_contracts (^1.0)"
    ]
