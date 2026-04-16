import importlib
import json
import sys
from pathlib import Path

from app.services.post_install_modules.playbook_validator import PlaybookValidator
from app.services.runtime_contract_registry import RuntimeContractRegistry
from backend.app.services.capability_registry import _ensure_capability_import_paths


LOCAL_CORE_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "mindscape-ai-local-core"
)
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"


def test_ensure_capability_import_paths_adds_runtime_contract_root():
    sys_path = []
    capability_dir = Path("/tmp/local-core/backend/app/capabilities/performance_direction")

    _ensure_capability_import_paths(sys_path, capability_dir)

    assert sys_path == [
        "/tmp/local-core/backend",
        "/tmp/local-core/backend/app",
        "/tmp/local-core/backend/app/capabilities",
        "/tmp/local-core/data/runtime_contracts",
    ]


def test_playbook_validator_env_includes_contract_import_roots():
    local_core_root = Path("/tmp/local-core")
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    validator = PlaybookValidator(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )

    env = validator._build_subprocess_env()

    assert env["PYTHONPATH"] == ":".join(
        [
            "/tmp/local-core",
            "/tmp/local-core/backend",
            "/tmp/local-core/backend/app",
            "/tmp/local-core/backend/app/capabilities",
            "/tmp/local-core/data/runtime_contracts",
        ]
    )


def test_runtime_contract_registry_writes_registry_and_alias_modules(tmp_path):
    registry = RuntimeContractRegistry(tmp_path)
    manifest = {
        "contract_exports": [
            {
                "contract_id": "visual_signal",
                "module": "capabilities.layer_asset_forge.schema.visual_signal",
                "version": "1.0.0",
                "legacy_aliases": ["shared.schemas.visual_signal"],
            }
        ]
    }

    result = registry.sync_pack_contracts("layer_asset_forge", manifest)

    registry_payload = json.loads(result.registry_path.read_text(encoding="utf-8"))
    alias_module = (
        tmp_path
        / "data"
        / "runtime_contracts"
        / "shared"
        / "schemas"
        / "visual_signal.py"
    )

    assert result.changed is True
    assert result.requires_restart is True
    assert result.alias_modules == ["shared.schemas.visual_signal"]
    assert registry_payload["contracts"] == [
        {
            "contract_id": "visual_signal",
            "legacy_aliases": ["shared.schemas.visual_signal"],
            "module": "capabilities.layer_asset_forge.schema.visual_signal",
            "provider_pack": "layer_asset_forge",
            "version": "1.0.0",
        }
    ]
    assert alias_module.read_text(encoding="utf-8") == (
        '"""Runtime-generated compatibility alias for '
        '`shared.schemas.visual_signal`."""\n\n'
        "from capabilities.layer_asset_forge.schema.visual_signal import *  # noqa: F401,F403\n"
    )


def test_runtime_contract_registry_removes_stale_exports_for_same_pack(tmp_path):
    registry = RuntimeContractRegistry(tmp_path)
    manifest = {
        "contract_exports": [
            {
                "contract_id": "visual_signal",
                "module": "capabilities.layer_asset_forge.schema.visual_signal",
                "version": "1.0.0",
                "legacy_aliases": ["shared.schemas.visual_signal"],
            }
        ]
    }
    registry.sync_pack_contracts("layer_asset_forge", manifest)

    result = registry.sync_pack_contracts("layer_asset_forge", {})
    registry_payload = json.loads(result.registry_path.read_text(encoding="utf-8"))

    assert result.changed is True
    assert result.alias_modules == []
    assert registry_payload["contracts"] == []


def test_shared_namespace_package_resolves_runtime_alias_root(tmp_path, monkeypatch):
    registry = RuntimeContractRegistry(tmp_path)
    registry.sync_pack_contracts(
        "test_contracts",
        {
            "contract_exports": [
                {
                    "contract_id": "runtime_contract_paths",
                    "module": "app.services.runtime_contract_paths",
                    "version": "1.0.0",
                    "legacy_aliases": ["shared.schemas.contract_paths_compat"],
                }
            ]
        },
    )

    runtime_contracts_root = tmp_path / "data" / "runtime_contracts"
    monkeypatch.syspath_prepend(str(runtime_contracts_root))
    monkeypatch.syspath_prepend(str(BACKEND_ROOT))

    for module_name in (
        "shared.schemas.contract_paths_compat",
        "shared.schemas",
        "shared",
    ):
        sys.modules.pop(module_name, None)

    importlib.invalidate_caches()

    import shared
    import shared.schemas
    from shared.schemas import contract_paths_compat

    assert any(
        path.endswith("data/runtime_contracts/shared") for path in shared.__path__
    )
    assert any(
        path.endswith("data/runtime_contracts/shared/schemas")
        for path in shared.schemas.__path__
    )
    assert hasattr(contract_paths_compat, "resolve_runtime_contracts_root")
