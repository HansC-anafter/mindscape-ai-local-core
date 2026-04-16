from pathlib import Path

from backend.app.app_bootstrap.startup_contract import (
    delete_preflight_contract,
    is_contract_trustworthy,
    read_preflight_contract,
    write_preflight_contract,
)
from backend.app.app_bootstrap.startup_seeded_activation import (
    record_startup_seeded_activation_pending,
)


def test_preflight_contract_roundtrip(tmp_path: Path):
    contract_path = tmp_path / "preflight.json"
    payload = {
        "written_at": 100.0,
        "db_fingerprint": "abc123",
        "critical_tables_ok": True,
        "db_ok": True,
    }

    write_preflight_contract(payload, path=contract_path)

    assert read_preflight_contract(path=contract_path) == payload

    delete_preflight_contract(path=contract_path)

    assert read_preflight_contract(path=contract_path) is None


def test_is_contract_trustworthy_enforces_ttl_and_fingerprint():
    payload = {
        "written_at": 100.0,
        "db_fingerprint": "abc123",
        "critical_tables_ok": True,
        "db_ok": True,
    }

    assert is_contract_trustworthy(
        payload,
        current_db_fingerprint="abc123",
        now_epoch=150.0,
        ttl_seconds=60,
    ) == (True, "trusted")
    assert is_contract_trustworthy(
        payload,
        current_db_fingerprint="mismatch",
        now_epoch=150.0,
        ttl_seconds=60,
    ) == (False, "fingerprint_mismatch")
    assert is_contract_trustworthy(
        payload,
        current_db_fingerprint="abc123",
        now_epoch=200.1,
        ttl_seconds=60,
    ) == (False, "stale")


def test_record_startup_seeded_activation_pending_preserves_existing_state():
    class FakeActivationService:
        def __init__(self):
            self.calls = []

        def get_state(self, pack_id):
            assert pack_id == "demo_pack"
            return {
                "install_state": "validation_pending",
                "activation_state": "pending_restart",
            }

        def record_activation_pending(self, **kwargs):
            self.calls.append(kwargs)
            return {"status": "unexpected"}

    service = FakeActivationService()

    result = record_startup_seeded_activation_pending(
        activation_service=service,
        pack_id="demo_pack",
        manifest={"code": "demo_pack"},
        manifest_path=Path("/tmp/demo_pack/manifest.yaml"),
    )

    assert result == {
        "install_state": "validation_pending",
        "activation_state": "pending_restart",
    }
    assert service.calls == []


def test_record_startup_seeded_activation_pending_records_when_state_not_preserved():
    class FakeActivationService:
        def __init__(self):
            self.calls = []

        def get_state(self, pack_id):
            assert pack_id == "demo_pack"
            return {"install_state": "installed", "activation_state": "active"}

        def record_activation_pending(self, **kwargs):
            self.calls.append(kwargs)
            return {"status": "recorded", **kwargs}

    service = FakeActivationService()
    manifest_path = Path("/tmp/demo_pack/manifest.yaml")

    result = record_startup_seeded_activation_pending(
        activation_service=service,
        pack_id="demo_pack",
        manifest={"code": "demo_pack"},
        manifest_path=manifest_path,
    )

    assert result["status"] == "recorded"
    assert service.calls == [
        {
            "pack_id": "demo_pack",
            "manifest": {"code": "demo_pack"},
            "manifest_path": manifest_path,
            "activation_mode": "startup_seeded",
        }
    ]
