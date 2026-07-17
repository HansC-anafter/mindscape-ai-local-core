from pathlib import Path

import pytest

from backend.app.services.deprecated import capability_installer as facade
from backend.app.services.deprecated.capability_installer import CapabilityInstaller


def test_deprecated_installer_only_creates_durable_job(monkeypatch, tmp_path: Path):
    mindpack = tmp_path / "demo.mindpack"
    mindpack.write_bytes(b"pack")
    calls = []

    class _Service:
        def create_file_upload_job(self, **kwargs):
            calls.append(kwargs)
            return {
                "install_id": "install-1",
                "state": "queued",
                "status_url": "/jobs/install-1",
            }

    monkeypatch.setattr(
        "backend.app.services.capability_install_jobs.CapabilityInstallJobService",
        _Service,
    )
    installer = CapabilityInstaller(tmp_path)

    accepted, result = installer.install_from_mindpack(mindpack)

    assert facade.CapabilityInstaller is CapabilityInstaller
    assert accepted is True
    assert result == {
        "accepted": True,
        "state": "queued",
        "install_id": "install-1",
        "status_url": "/jobs/install-1",
        "validation_requested": True,
    }
    assert calls[0]["content"] == b"pack"


def test_deprecated_direct_install_path_is_forbidden(tmp_path: Path):
    installer = CapabilityInstaller(tmp_path)
    with pytest.raises(RuntimeError, match="legacy_direct_capability_install_forbidden"):
        installer._install_capability()
