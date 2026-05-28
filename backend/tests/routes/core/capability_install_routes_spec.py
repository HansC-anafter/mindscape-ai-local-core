import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.app.routes.core import capability_install
from backend.app.routes.core.capability_install_core import pipeline as capability_install_pipeline
from backend.app.services.install_result import InstallResult as RealInstallResult
from backend.app.services import (
    runtime_assets_installer as runtime_assets_installer_module,
)


@pytest.mark.asyncio
async def test_run_install_pipeline_offloads_blocking_phases(monkeypatch, tmp_path: Path):
    root = tmp_path / "local-core"
    (root / "backend" / "app" / "capabilities").mkdir(parents=True)
    (root / "backend" / "playbooks" / "specs").mkdir(parents=True)
    (root / "backend" / "i18n" / "playbooks").mkdir(parents=True)

    extract_dir = tmp_path / "extract"
    cap_dir = extract_dir / "ig"
    cap_dir.mkdir(parents=True)
    (cap_dir / "manifest.yaml").write_text(
        "code: ig\nversion: 1.2.3\nplaybooks: []\n",
        encoding="utf-8",
    )

    class FakeInstallResult:
        def __init__(self, capability_code):
            self.capability_code = capability_code
            self.warnings = []
            self.errors = []
            self.migration_status = {"ig": "applied"}

        def add_warning(self, message):
            self.warnings.append(message)

        def add_error(self, message):
            self.errors.append(message)

        def has_errors(self):
            return bool(self.errors)

    class FakeExtractor:
        def __init__(self, _root):
            pass

        def extract(self, _mindpack_path):
            return True, extract_dir, "ig", cap_dir

    class FakeValidator:
        def __init__(self, _root):
            pass

        def validate(self, *_args, **_kwargs):
            return True, [], []

    class FakePlaybookInstaller:
        def __init__(self):
            self.capabilities_dir = None
            self.specs_dir = None
            self.i18n_base_dir = None
            self.local_core_root = None

        def _install_playbooks(self, *_args, **_kwargs):
            return None

        def _validate_tools_direct_call(self, *_args, **_kwargs):
            return None

    class FakeRuntimeInstaller:
        def __init__(self, **_kwargs):
            pass

        def install_all(self, *_args, **_kwargs):
            return None

        def execute_migrations(self, *_args, **_kwargs):
            return None

    class FakePostInstallHandler:
        def __init__(self, **_kwargs):
            pass

        def run_required_tasks(self, *_args, **_kwargs):
            return None

    class FakeRegistry:
        def __init__(self):
            self._capabilities_cache = {}
            self._tools_cache = {}

    class FakeContractSync:
        requires_restart = False
        alias_modules = []

    class FakeRuntimeContractRegistry:
        def __init__(self, _root):
            pass

        def sync_pack_contracts(self, *_args, **_kwargs):
            return FakeContractSync()

    class FakeModelRouteSlotRegistry:
        def extract_pack_slots_from_manifest(self, **_kwargs):
            return []

    def fake_get_registry():
        return FakeRegistry()

    def fake_load_capabilities(reset=False):
        return None

    def fake_reload_capability_routes(*_args, **_kwargs):
        return {"ok": True}

    fake_modules = {
        "app.services.mindpack_extractor": types.SimpleNamespace(
            MindpackExtractor=FakeExtractor
        ),
        "app.services.manifest_validator": types.SimpleNamespace(
            ManifestValidator=FakeValidator
        ),
        "app.services.playbook_installer": types.SimpleNamespace(
            PlaybookInstaller=FakePlaybookInstaller
        ),
        "app.services.runtime_assets_installer": types.SimpleNamespace(
            RuntimeAssetsInstaller=FakeRuntimeInstaller
        ),
        "app.services.post_install": types.SimpleNamespace(
            PostInstallHandler=FakePostInstallHandler
        ),
        "app.services.install_result": types.SimpleNamespace(
            InstallResult=FakeInstallResult
        ),
        "app.services.runtime_contract_registry": types.SimpleNamespace(
            RuntimeContractRegistry=FakeRuntimeContractRegistry
        ),
        "app.services.capability_registry": types.SimpleNamespace(
            get_registry=fake_get_registry,
            load_capabilities=fake_load_capabilities,
        ),
        "app.services.capability_reload_manager": types.SimpleNamespace(
            hot_reload_enabled=lambda: True,
            reload_capability_routes=fake_reload_capability_routes,
        ),
        "backend.app.services.model_route_slot_registry": types.SimpleNamespace(
            ModelRouteSlotRegistry=FakeModelRouteSlotRegistry,
        ),
    }
    for name, module in fake_modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    class FakeInstalledPacksStore:
        def upsert_pack(self, **_kwargs):
            return None

    class FakePackActivationService:
        def record_install_outcome(self, **_kwargs):
            return {"status": "ok"}

        def record_embedding_succeeded(self, **_kwargs):
            return None

        def record_embedding_failed(self, **_kwargs):
            return None

    async def fake_refresh_tool_rag_corpus(**_kwargs):
        return None, 0, "skipped"

    async def fake_run_post_install_followups(**_kwargs):
        return None

    recorded = []

    async def fake_run_in_threadpool(func, *args, **kwargs):
        recorded.append(getattr(func, "__name__", repr(func)))
        return func(*args, **kwargs)

    monkeypatch.setattr(capability_install, "_resolve_local_core_root", lambda: root)
    monkeypatch.setattr(capability_install_pipeline, "_resolve_local_core_root", lambda: root)
    monkeypatch.setattr(
        capability_install_pipeline,
        "ensure_core_write_ready",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        capability_install,
        "installed_packs_store",
        FakeInstalledPacksStore(),
        raising=False,
    )
    monkeypatch.setattr(
        capability_install_pipeline,
        "installed_packs_store",
        FakeInstalledPacksStore(),
    )
    monkeypatch.setattr(
        capability_install,
        "pack_activation_service",
        FakePackActivationService(),
        raising=False,
    )
    monkeypatch.setattr(
        capability_install_pipeline,
        "pack_activation_service",
        FakePackActivationService(),
    )
    monkeypatch.setattr(
        capability_install,
        "refresh_tool_rag_corpus",
        fake_refresh_tool_rag_corpus,
        raising=False,
    )
    monkeypatch.setattr(
        capability_install_pipeline,
        "refresh_tool_rag_corpus",
        fake_refresh_tool_rag_corpus,
        raising=False,
    )
    monkeypatch.setattr(
        capability_install,
        "run_in_threadpool",
        fake_run_in_threadpool,
        raising=False,
    )
    monkeypatch.setattr(
        capability_install_pipeline,
        "run_in_threadpool",
        fake_run_in_threadpool,
    )
    monkeypatch.setattr(
        capability_install_pipeline,
        "run_post_install_followups",
        fake_run_post_install_followups,
    )

    result = await capability_install.run_install_pipeline(
        fastapi_app=object(),
        mindpack_path=tmp_path / "sample.mindpack",
        allow_overwrite=False,
        overwrite_review_confirmation="",
        source_label="test-install",
    )

    assert result.success is True
    normalized = {
        name[len("fake_") :] if name.startswith("fake_") else name for name in recorded
    }
    assert {
        "extract",
        "validate",
        "_install_playbooks",
        "install_all",
            "execute_migrations",
            "run_required_tasks",
            "_sync_install_time_registries",
            "reload_capability_routes",
            "upsert_pack",
            "record_install_outcome",
    }.issubset(normalized)


@pytest.mark.asyncio
async def test_run_install_pipeline_installs_capability_scripts(monkeypatch, tmp_path: Path):
    root = tmp_path / "local-core"
    (root / "backend" / "app" / "capabilities").mkdir(parents=True)
    (root / "backend" / "playbooks" / "specs").mkdir(parents=True)
    (root / "backend" / "i18n" / "playbooks").mkdir(parents=True)

    extract_dir = tmp_path / "extract"
    cap_dir = extract_dir / "ig"
    scripts_dir = cap_dir / "scripts"
    nested_dir = scripts_dir / "nested"
    pycache_dir = scripts_dir / "__pycache__"
    nested_dir.mkdir(parents=True)
    pycache_dir.mkdir(parents=True)
    (cap_dir / "manifest.yaml").write_text(
        "code: ig\nversion: 1.2.3\nplaybooks: []\n",
        encoding="utf-8",
    )
    (scripts_dir / "__init__.py").write_text("# package\n", encoding="utf-8")
    (scripts_dir / "ig_login_helper.py").write_text("HELPER = True\n", encoding="utf-8")
    (scripts_dir / "run_helper.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (scripts_dir / ".DS_Store").write_text("ignore-me\n", encoding="utf-8")
    (nested_dir / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (pycache_dir / "ig_login_helper.cpython-312.pyc").write_bytes(b"compiled")

    class FakeExtractor:
        def __init__(self, _root):
            pass

        def extract(self, _mindpack_path):
            return True, extract_dir, "ig", cap_dir

    class FakeValidator:
        def __init__(self, _root):
            pass

        def validate(self, *_args, **_kwargs):
            return True, [], []

    class FakePlaybookInstaller:
        def __init__(self):
            self.capabilities_dir = None
            self.specs_dir = None
            self.i18n_base_dir = None
            self.local_core_root = None

        def _install_playbooks(self, *_args, **_kwargs):
            return None

        def _validate_tools_direct_call(self, *_args, **_kwargs):
            return None

    class FakePostInstallHandler:
        def __init__(self, **_kwargs):
            pass

        def run_required_tasks(self, *_args, **_kwargs):
            return None

    class FakeRegistry:
        def __init__(self):
            self._capabilities_cache = {}
            self._tools_cache = {}

    class FakeContractSync:
        requires_restart = False
        alias_modules = []

    class FakeRuntimeContractRegistry:
        def __init__(self, _root):
            pass

        def sync_pack_contracts(self, *_args, **_kwargs):
            return FakeContractSync()

    class FakeModelRouteSlotRegistry:
        def extract_pack_slots_from_manifest(self, **_kwargs):
            return []

    def fake_get_registry():
        return FakeRegistry()

    def fake_load_capabilities(reset=False):
        return None

    def fake_reload_capability_routes(*_args, **_kwargs):
        return {"ok": True}

    fake_modules = {
        "app.services.mindpack_extractor": types.SimpleNamespace(
            MindpackExtractor=FakeExtractor
        ),
        "app.services.manifest_validator": types.SimpleNamespace(
            ManifestValidator=FakeValidator
        ),
        "app.services.playbook_installer": types.SimpleNamespace(
            PlaybookInstaller=FakePlaybookInstaller
        ),
        "app.services.runtime_assets_installer": runtime_assets_installer_module,
        "app.services.post_install": types.SimpleNamespace(
            PostInstallHandler=FakePostInstallHandler
        ),
        "app.services.install_result": types.SimpleNamespace(
            InstallResult=RealInstallResult
        ),
        "app.services.runtime_contract_registry": types.SimpleNamespace(
            RuntimeContractRegistry=FakeRuntimeContractRegistry
        ),
        "app.services.capability_registry": types.SimpleNamespace(
            get_registry=fake_get_registry,
            load_capabilities=fake_load_capabilities,
        ),
        "app.services.capability_reload_manager": types.SimpleNamespace(
            hot_reload_enabled=lambda: True,
            reload_capability_routes=fake_reload_capability_routes,
        ),
        "backend.app.services.model_route_slot_registry": types.SimpleNamespace(
            ModelRouteSlotRegistry=FakeModelRouteSlotRegistry,
        ),
    }
    for name, module in fake_modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    class FakeInstalledPacksStore:
        def upsert_pack(self, **_kwargs):
            return None

    class FakePackActivationService:
        def record_install_outcome(self, **_kwargs):
            return {"status": "ok"}

        def record_embedding_succeeded(self, **_kwargs):
            return None

        def record_embedding_failed(self, **_kwargs):
            return None

    async def fake_refresh_tool_rag_corpus(**_kwargs):
        return None, 0, "skipped"

    async def fake_run_post_install_followups(**_kwargs):
        return None

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(capability_install, "_resolve_local_core_root", lambda: root)
    monkeypatch.setattr(capability_install_pipeline, "_resolve_local_core_root", lambda: root)
    monkeypatch.setattr(
        capability_install_pipeline,
        "ensure_core_write_ready",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        capability_install,
        "installed_packs_store",
        FakeInstalledPacksStore(),
        raising=False,
    )
    monkeypatch.setattr(
        capability_install_pipeline,
        "installed_packs_store",
        FakeInstalledPacksStore(),
    )
    monkeypatch.setattr(
        capability_install,
        "pack_activation_service",
        FakePackActivationService(),
        raising=False,
    )
    monkeypatch.setattr(
        capability_install_pipeline,
        "pack_activation_service",
        FakePackActivationService(),
    )
    monkeypatch.setattr(
        capability_install,
        "refresh_tool_rag_corpus",
        fake_refresh_tool_rag_corpus,
        raising=False,
    )
    monkeypatch.setattr(
        capability_install_pipeline,
        "refresh_tool_rag_corpus",
        fake_refresh_tool_rag_corpus,
        raising=False,
    )
    monkeypatch.setattr(
        capability_install,
        "run_in_threadpool",
        fake_run_in_threadpool,
        raising=False,
    )
    monkeypatch.setattr(
        capability_install_pipeline,
        "run_in_threadpool",
        fake_run_in_threadpool,
    )
    monkeypatch.setattr(
        capability_install_pipeline,
        "run_post_install_followups",
        fake_run_post_install_followups,
    )

    result = await capability_install.run_install_pipeline(
        fastapi_app=object(),
        mindpack_path=tmp_path / "sample.mindpack",
        allow_overwrite=False,
        overwrite_review_confirmation="",
        source_label="test-install",
    )

    target_scripts_dir = root / "backend" / "app" / "capabilities" / "ig" / "scripts"
    assert result.success is True
    assert (target_scripts_dir / "__init__.py").exists()
    assert (target_scripts_dir / "ig_login_helper.py").read_text(encoding="utf-8") == "HELPER = True\n"
    assert (target_scripts_dir / "run_helper.sh").read_text(encoding="utf-8") == "#!/usr/bin/env bash\n"
    assert (target_scripts_dir / "nested" / "config.yaml").read_text(encoding="utf-8") == "version: 1\n"
    assert not (target_scripts_dir / ".DS_Store").exists()
    assert not (target_scripts_dir / "__pycache__" / "ig_login_helper.cpython-312.pyc").exists()
