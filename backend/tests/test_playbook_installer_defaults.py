from pathlib import Path

from backend.app.services.playbook_installer import PlaybookInstaller


def test_playbook_installer_bootstraps_default_paths():
    installer = PlaybookInstaller()

    assert (installer.local_core_root / "backend").exists()
    assert installer.capabilities_dir == installer.local_core_root / "backend" / "app" / "capabilities"
    assert installer.specs_dir == installer.local_core_root / "backend" / "playbooks" / "specs"
    assert installer.i18n_base_dir == installer.local_core_root / "backend" / "i18n" / "playbooks"


def test_validate_tools_direct_call_reports_missing_spec_with_default_paths():
    installer = PlaybookInstaller()

    errors, warnings = installer._validate_tools_direct_call("missing", "missing")

    assert errors == ["Playbook spec not found: missing.json"]
    assert warnings == []
