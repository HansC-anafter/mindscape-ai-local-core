import importlib
import sys
from pathlib import Path

import pytest
import yaml


LOCAL_CORE_REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "mindscape-ai-local-core"
)
BACKEND_ROOT = LOCAL_CORE_REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import capability_registry  # noqa: E402
from app.services.runtime.capability_runtime_loader import (  # noqa: E402
    CapabilityRuntimeLoader,
)
from app.services.runtime_contract_registry import RuntimeContractRegistry  # noqa: E402


def _clear_shared_schema_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "shared" or module_name.startswith("shared.schemas"):
            sys.modules.pop(module_name, None)
    importlib.invalidate_caches()


def _clear_capability_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "capabilities" or module_name.startswith("capabilities."):
            sys.modules.pop(module_name, None)
    importlib.invalidate_caches()


def _write_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "__init__.py").write_text("", encoding="utf-8")


def _write_manifest(pack_dir: Path, manifest: dict) -> None:
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )


def _write_contract_provider(capabilities_dir: Path) -> dict:
    provider_dir = capabilities_dir / "provider_pack"
    _write_init(capabilities_dir)
    _write_init(provider_dir)
    _write_init(provider_dir / "schema")
    (provider_dir / "schema" / "example_contract.py").write_text(
        'SENTINEL = "canonical-contract-ok"\n',
        encoding="utf-8",
    )
    manifest = {
        "code": "provider_pack",
        "version": "1.0.0",
        "portability": {
            "min_local_core_version": "0.9.0",
            "environments": ["local-core"],
        },
        "contract_exports": [
            {
                "contract_id": "example_contract",
                "module": "capabilities.provider_pack.schema.example_contract",
                "version": "1.0.0",
                "legacy_aliases": ["shared.schemas.example_contract"],
            }
        ],
        "tools": [],
    }
    _write_manifest(provider_dir, manifest)
    return manifest


def _write_consumer_pack(capabilities_dir: Path) -> None:
    consumer_dir = capabilities_dir / "consumer_pack"
    _write_init(consumer_dir)
    _write_init(consumer_dir / "tools")
    (consumer_dir / "tools" / "read_contract.py").write_text(
        (
            "from shared.schemas.example_contract import SENTINEL\n\n"
            "def read_contract():\n"
            "    return {'sentinel': SENTINEL}\n"
        ),
        encoding="utf-8",
    )
    (consumer_dir / "tools" / "read_contract_async.py").write_text(
        (
            "from shared.schemas.example_contract import SENTINEL\n\n"
            "async def read_contract_async():\n"
            "    return {'sentinel': SENTINEL}\n"
        ),
        encoding="utf-8",
    )
    _write_manifest(
        consumer_dir,
        {
            "code": "consumer_pack",
            "version": "1.0.0",
            "portability": {
                "min_local_core_version": "0.9.0",
                "environments": ["local-core"],
            },
            "contract_imports": [
                {
                    "contract_id": "example_contract",
                    "provider_pack": "provider_pack",
                    "version_range": "^1.0",
                }
            ],
            "tools": [
                {
                    "name": "read_contract",
                    "backend": "capabilities.consumer_pack.tools.read_contract:read_contract",
                },
                {
                    "name": "read_contract_async",
                    "backend": (
                        "capabilities.consumer_pack.tools.read_contract_async:"
                        "read_contract_async"
                    ),
                },
            ],
        },
    )


def _build_local_core_tree(tmp_path: Path) -> tuple[Path, Path, dict]:
    local_core_root = tmp_path / "mindscape-ai-local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    stale_shared_dir = local_core_root / "backend" / "shared" / "schemas"
    _write_init(local_core_root / "backend" / "shared")
    _write_init(stale_shared_dir)
    (stale_shared_dir / "example_contract.py").write_text(
        'SENTINEL = "stale-host-mirror"\n',
        encoding="utf-8",
    )
    provider_manifest = _write_contract_provider(capabilities_dir)
    _write_consumer_pack(capabilities_dir)
    RuntimeContractRegistry(local_core_root).sync_pack_contracts(
        "provider_pack",
        provider_manifest,
    )
    _clear_shared_schema_modules()
    _clear_capability_modules()
    return local_core_root, capabilities_dir, provider_manifest


def _reset_registry() -> None:
    capability_registry._registry.capabilities.clear()
    capability_registry._registry.tools.clear()
    capability_registry.CAPABILITY_REGISTRY.clear()
    capability_registry.TOOL_REGISTRY.clear()


def test_capability_registry_sync_tool_resolves_runtime_contract_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _local_core_root, capabilities_dir, _manifest = _build_local_core_tree(tmp_path)
    original_sys_path = list(sys.path)
    monkeypatch.setattr(
        capability_registry.PackActivationService,
        "record_activation_succeeded",
        lambda self, **kwargs: None,
    )

    try:
        capability_registry.load_capabilities(capabilities_dir, reset=True)
        result = capability_registry.call_tool("consumer_pack", "read_contract")
    finally:
        _reset_registry()
        _clear_shared_schema_modules()
        _clear_capability_modules()
        sys.path[:] = original_sys_path

    assert result == {"sentinel": "canonical-contract-ok"}


@pytest.mark.asyncio
async def test_capability_registry_async_tool_resolves_runtime_contract_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _local_core_root, capabilities_dir, _manifest = _build_local_core_tree(tmp_path)
    original_sys_path = list(sys.path)
    monkeypatch.setattr(
        capability_registry.PackActivationService,
        "record_activation_succeeded",
        lambda self, **kwargs: None,
    )

    try:
        capability_registry.load_capabilities(capabilities_dir, reset=True)
        result = await capability_registry.call_tool_async(
            "consumer_pack",
            "read_contract_async",
        )
    finally:
        _reset_registry()
        _clear_shared_schema_modules()
        _clear_capability_modules()
        sys.path[:] = original_sys_path

    assert result == {"sentinel": "canonical-contract-ok"}


def test_runtime_provider_loader_resolves_runtime_contract_alias(tmp_path: Path):
    _local_core_root, capabilities_dir, _manifest = _build_local_core_tree(tmp_path)
    runtime_dir = capabilities_dir / "runtime_pack"
    _write_init(runtime_dir)
    (runtime_dir / "runtime_provider.py").write_text(
        (
            "from shared.schemas.example_contract import SENTINEL\n"
            "from backend.app.core.runtime_port import RuntimePort, ExecutionResult\n\n"
            "class DemoRuntime(RuntimePort):\n"
            "    def __init__(self, store=None):\n"
            "        self.store = store\n\n"
            "    @property\n"
            "    def name(self):\n"
            "        return f'demo-{SENTINEL}'\n\n"
            "    @property\n"
            "    def capabilities(self):\n"
            "        return ['contract_alias']\n\n"
            "    def supports(self, execution_profile):\n"
            "        return True\n\n"
            "    async def execute(self, playbook_run, context, inputs=None):\n"
            "        return ExecutionResult(status='completed', execution_id='demo')\n\n"
            "    async def resume(self, execution_id, checkpoint):\n"
            "        return ExecutionResult(status='completed', execution_id=execution_id)\n\n"
            "    async def pause(self, execution_id):\n"
            "        return ExecutionResult(status='paused', execution_id=execution_id)\n\n"
            "    async def cancel(self, execution_id, reason=None):\n"
            "        return ExecutionResult(status='cancelled', execution_id=execution_id)\n\n"
            "    async def get_status(self, execution_id):\n"
            "        return ExecutionResult(status='completed', execution_id=execution_id)\n"
        ),
        encoding="utf-8",
    )
    _write_manifest(
        runtime_dir,
        {
            "code": "runtime_pack",
            "version": "1.0.0",
            "type": "system_runtime",
            "portability": {
                "min_local_core_version": "0.9.0",
                "environments": ["local-core"],
            },
            "runtime_provider": {"class": "runtime_provider.DemoRuntime"},
        },
    )

    original_sys_path = list(sys.path)
    try:
        runtimes = CapabilityRuntimeLoader([capabilities_dir]).load_all_runtime_providers()
    finally:
        _clear_shared_schema_modules()
        _clear_capability_modules()
        sys.path[:] = original_sys_path

    assert [runtime.name for runtime in runtimes] == ["demo-canonical-contract-ok"]
