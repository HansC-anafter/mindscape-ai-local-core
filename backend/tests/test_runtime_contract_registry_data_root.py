from pathlib import Path

from backend.app.services.runtime_contract_registry import RuntimeContractRegistry


def _contract_manifest() -> dict:
    return {
        "code": "provider_pack",
        "contract_exports": [
            {
                "contract_id": "example_contract",
                "module": "capabilities.provider_pack.schema.example_contract",
                "version": "1.0.0",
                "legacy_aliases": ["shared.schemas.example_contract"],
            }
        ],
    }


def test_runtime_contract_registry_generates_alias_under_data_root(tmp_path: Path):
    local_core_root = tmp_path / "mindscape-ai-local-core"
    registry = RuntimeContractRegistry(local_core_root)

    result = registry.sync_pack_contracts("provider_pack", _contract_manifest())

    alias_path = (
        local_core_root
        / "data"
        / "runtime_contracts"
        / "shared"
        / "schemas"
        / "example_contract.py"
    )
    assert result.changed is True
    assert result.requires_restart is True
    assert result.alias_modules == ["shared.schemas.example_contract"]
    assert alias_path.exists()
    assert (
        "from capabilities.provider_pack.schema.example_contract import *"
        in alias_path.read_text(encoding="utf-8")
    )
    assert not (
        local_core_root
        / "backend"
        / "shared"
        / "schemas"
        / "example_contract.py"
    ).exists()


def test_runtime_contract_registry_rewrites_retired_aliases(tmp_path: Path):
    local_core_root = tmp_path / "mindscape-ai-local-core"
    registry = RuntimeContractRegistry(local_core_root)

    registry.sync_pack_contracts("provider_pack", _contract_manifest())
    result = registry.sync_pack_contracts(
        "provider_pack",
        {
            "code": "provider_pack",
            "contract_exports": [
                {
                    "contract_id": "example_contract",
                    "module": "capabilities.provider_pack.schema.example_contract",
                    "version": "1.0.1",
                    "legacy_aliases": [],
                }
            ],
        },
    )

    alias_path = (
        local_core_root
        / "data"
        / "runtime_contracts"
        / "shared"
        / "schemas"
        / "example_contract.py"
    )
    assert result.changed is True
    assert result.alias_modules == []
    assert not alias_path.exists()
