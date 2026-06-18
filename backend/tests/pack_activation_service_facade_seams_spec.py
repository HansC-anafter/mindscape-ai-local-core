from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.services import pack_activation_service as facade
from backend.app.services.install_result import InstallResult
from backend.app.services.pack_activation_service import (
    PackActivationRecord,
    PackActivationService,
    _utc_now,
)
from backend.app.services.stores.pack_activation_state_store import PackActivationStateStore


class _FakeActivationStore:
    def __init__(self) -> None:
        self.state: Dict[str, Dict[str, Any]] = {}

    def get_state(self, pack_id: str) -> Optional[Dict[str, Any]]:
        value = self.state.get(pack_id)
        return dict(value) if value else None

    def list_states_by_pack_id(self) -> Dict[str, Dict[str, Any]]:
        return {pack_id: dict(value) for pack_id, value in self.state.items()}

    def upsert_state(self, **payload: Any) -> Dict[str, Any]:
        payload.pop("allow_install_state_regression", None)
        self.state[payload["pack_id"]] = dict(payload)
        return dict(payload)


def _manifest() -> Dict[str, Any]:
    return {
        "code": "demo-pack",
        "routes": ["/capabilities/demo"],
        "apis": [{"prefix": "/api/demo"}],
        "tools": [{"name": "demo_tool"}],
    }


def test_pack_activation_service_facade_exports_public_surface() -> None:
    assert facade.PackActivationService is PackActivationService
    assert facade.PackActivationRecord is PackActivationRecord
    assert isinstance(_utc_now(), datetime)
    assert isinstance(facade._utc_now(), datetime)
    assert hasattr(PackActivationService, "_compute_manifest_hash")
    assert hasattr(PackActivationService, "_load_runtime_manifest")


def test_record_install_outcome_uses_fake_store_and_preserves_hot_reload_state() -> None:
    store = _FakeActivationStore()
    service = PackActivationService(store=store)  # type: ignore[arg-type]
    result = InstallResult(capability_code="demo-pack")
    result.extend_installed("api_endpoints", ["/api/demo"])

    state = service.record_install_outcome(
        pack_id="demo-pack",
        manifest=_manifest(),
        install_result=result,
        enabled=True,
        hot_reload_performed=True,
        restart_required=False,
    )

    assert state["pack_family"] == "hybrid"
    assert state["install_state"] == "installed"
    assert state["migration_state"] == "not_applicable"
    assert state["activation_state"] == "active"
    assert state["activation_mode"] == "install_hot_reload"
    assert state["embedding_state"] == "pending"
    assert state["registered_prefixes"] == ["/capabilities/demo", "/api/demo"]
    assert state["manifest_hash"]
    assert state["activated_at"] is not None
    assert store.get_state("demo-pack") == state


def test_runtime_transitions_preserve_state_with_fake_store() -> None:
    store = _FakeActivationStore()
    service = PackActivationService(store=store)  # type: ignore[arg-type]
    manifest = _manifest()

    active = service.record_activation_succeeded(
        pack_id="demo-pack",
        manifest=manifest,
        activation_mode="manual_enable",
        registered_prefixes=["/runtime/demo"],
    )
    assert active["activation_state"] == "active"
    assert active["activation_mode"] == "manual_enable"
    assert active["install_state"] == "installed"
    assert active["registered_prefixes"] == ["/runtime/demo"]

    pending = service.record_validation_pending(
        pack_id="demo-pack",
        manifest=manifest,
    )
    assert pending is not None
    assert pending["install_state"] == "validation_pending"
    assert pending["activation_state"] == "active"
    assert pending["activation_mode"] == "manual_enable"

    failed = service.record_validation_failed(
        pack_id="demo-pack",
        manifest=manifest,
        error="validation failed",
    )
    assert failed is not None
    assert failed["install_state"] == "validation_failed"
    assert failed["last_error"] == "validation failed"

    recovered = service.record_validation_succeeded(
        pack_id="demo-pack",
        manifest=manifest,
    )
    assert recovered is not None
    assert recovered["install_state"] == "installed"
    assert recovered["last_error"] is None

    latest = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    observed = service.record_embedding_observed(
        pack_id="demo-pack",
        row_count=1,
        latest_updated_at=latest,
        manifest=manifest,
    )
    assert observed is not None
    assert observed["activation_state"] == "active"
    assert observed["embedding_state"] == "indexed"
    assert observed["embedding_error"] is None
    assert observed["embeddings_updated_at"] == latest


def test_activation_state_store_blocks_same_manifest_validation_pending_regression() -> None:
    assert (
        PackActivationStateStore._resolve_install_state_for_upsert(
            existing_install_state="installed",
            existing_manifest_hash="same-hash",
            incoming_install_state="validation_pending",
            incoming_manifest_hash="same-hash",
            allow_install_state_regression=False,
        )
        == "installed"
    )
    assert (
        PackActivationStateStore._resolve_install_state_for_upsert(
            existing_install_state="installed",
            existing_manifest_hash="old-hash",
            incoming_install_state="validation_pending",
            incoming_manifest_hash="new-hash",
            allow_install_state_regression=False,
        )
        == "validation_pending"
    )
    assert (
        PackActivationStateStore._resolve_install_state_for_upsert(
            existing_install_state="installed",
            existing_manifest_hash="same-hash",
            incoming_install_state="validation_pending",
            incoming_manifest_hash="same-hash",
            allow_install_state_regression=True,
        )
        == "validation_pending"
    )
