import importlib
import sys
from pathlib import Path

from app.services.runtime_assets_installer_core.candidate_import_scope import (
    CandidateCapabilityImportScope,
)


def test_candidate_import_scope_exposes_first_install_package(tmp_path: Path) -> None:
    capability_code = "candidate_import_scope_probe"
    capabilities_dir = tmp_path / "capabilities"
    helper_dir = capabilities_dir / capability_code / "migrations" / "helpers"
    helper_dir.mkdir(parents=True)
    for package_dir in (
        capabilities_dir / capability_code,
        capabilities_dir / capability_code / "migrations",
        helper_dir,
    ):
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (helper_dir / "probe.py").write_text("VALUE = 'candidate'\n", encoding="utf-8")

    module_prefix = f"app.capabilities.{capability_code}"
    scope = CandidateCapabilityImportScope(capabilities_dir, capability_code)
    scope.activate()
    try:
        module = importlib.import_module(f"{module_prefix}.migrations.helpers.probe")
        assert module.VALUE == "candidate"
    finally:
        for module_name in list(sys.modules):
            if module_name == module_prefix or module_name.startswith(
                f"{module_prefix}."
            ):
                sys.modules.pop(module_name, None)
        scope.restore()

    capabilities_package = importlib.import_module("app.capabilities")
    assert capabilities_dir.as_posix() not in {
        str(path) for path in capabilities_package.__path__
    }
