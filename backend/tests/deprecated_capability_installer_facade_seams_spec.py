from pathlib import Path

from backend.app.services.deprecated import capability_installer as facade
from backend.app.services.deprecated.capability_installer import (
    CapabilityInstaller,
    LegacyResult,
)
from backend.app.services.install_result import InstallResult


class _FakeRuntimeAssetsInstaller:
    def __init__(self) -> None:
        self.calls = []

    def install_tools(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ) -> None:
        self.calls.append(("install_tools", cap_dir, capability_code))
        result.capability_code = capability_code
        result.add_installed("tools", f"{capability_code}_tool.py")

    def execute_migrations(self, capability_code: str, result: InstallResult) -> None:
        self.calls.append(("execute_migrations", capability_code))
        result.migration_status = {capability_code: "applied"}

    def install_manifest(
        self, cap_dir: Path, capability_code: str, manifest: dict
    ) -> None:
        self.calls.append(("install_manifest", cap_dir, capability_code, manifest))

    def install_bundles(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ) -> None:
        self.calls.append(("install_bundles", cap_dir, capability_code))
        result.add_installed("bundles", f"{capability_code}/bundle")


def _installer_with_fake_runtime() -> CapabilityInstaller:
    installer = CapabilityInstaller.__new__(CapabilityInstaller)
    installer.local_core_root = Path("/tmp/local-core")
    installer._runtime_assets_installer = _FakeRuntimeAssetsInstaller()
    return installer


def test_deprecated_capability_installer_facade_exports_legacy_surface() -> None:
    assert facade.CapabilityInstaller is CapabilityInstaller
    assert facade.LegacyResult is LegacyResult
    assert isinstance(CapabilityInstaller._create_result(), InstallResult)
    assert hasattr(CapabilityInstaller, "_install_tools")
    assert hasattr(CapabilityInstaller, "_run_python_script")
    assert CapabilityInstaller._run_python_script.__module__.endswith(
        "capability_installer_runtime_assets"
    )


def test_runtime_asset_delegate_syncs_legacy_dict_result() -> None:
    installer = _installer_with_fake_runtime()
    legacy_result = {}

    installer._install_tools(Path("/tmp/cap"), "demo", legacy_result)

    assert legacy_result["capability_code"] == "demo"
    assert legacy_result["installed"]["tools"] == ["demo_tool.py"]
    assert installer._runtime_assets_installer.calls == [
        ("install_tools", Path("/tmp/cap"), "demo")
    ]


def test_runtime_asset_delegate_preserves_install_result_instance() -> None:
    installer = _installer_with_fake_runtime()
    result = InstallResult(capability_code="demo")

    installer._execute_migrations("demo", result)
    installer._install_bundles(Path("/tmp/cap"), "demo", result)

    assert result.migration_status == {"demo": "applied"}
    assert result.installed["bundles"] == ["demo/bundle"]
    assert installer._runtime_assets_installer.calls == [
        ("execute_migrations", "demo"),
        ("install_bundles", Path("/tmp/cap"), "demo"),
    ]


def test_install_manifest_delegate_does_not_require_result_coercion() -> None:
    installer = _installer_with_fake_runtime()
    manifest = {"code": "demo"}

    installer._install_manifest(Path("/tmp/cap"), "demo", manifest)

    assert installer._runtime_assets_installer.calls == [
        ("install_manifest", Path("/tmp/cap"), "demo", manifest)
    ]
