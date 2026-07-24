import pytest
from fastapi import HTTPException

from backend.app.database.write_readiness import (
    DatabaseWriteNotReadyError,
    DatabaseWriteReadiness,
)
from backend.app.services import capability_install_jobs
from backend.app.services import pack_install_reconciliation
from backend.app.services.capability_install_jobs import CapabilityInstallJobService
from backend.app.services.capability_install_jobs_core import executor


class _FakeStore:
    def __init__(self):
        self.waiting = None
        self.failed = None

    def claim_next_job(self):
        return {
            "install_id": "job-1",
            "source_kind": "file_upload",
            "source_payload": {
                "mindpack_path": "/tmp/demo.mindpack",
                "allow_overwrite": False,
                "overwrite_review_confirmation": "",
            },
        }

    def mark_waiting_db(self, install_id, *, reason, retry_after_seconds):
        self.waiting = {
            "install_id": install_id,
            "state": "waiting_db",
            "reason": reason,
            "retry_after_seconds": retry_after_seconds,
        }
        return self.waiting

    def mark_failed(self, install_id, *, error, result_payload=None):
        self.failed = {
            "install_id": install_id,
            "state": "failed",
            "error": error,
            "result_payload": result_payload or {},
        }
        return self.failed


class _PendingActivationStore:
    def __init__(self, result_payload):
        self.result_payload = result_payload
        self.succeeded_payload = None

    def get_job(self, install_id):
        return {
            "install_id": install_id,
            "state": "pending_execution_activation",
            "result_payload": self.result_payload,
        }

    def mark_succeeded(self, install_id, *, result_payload):
        self.succeeded_payload = result_payload
        return {
            "install_id": install_id,
            "state": "succeeded",
            "result_payload": result_payload,
        }


class _ActivationService:
    def __init__(self, state):
        self.state = state

    def get_state(self, pack_id):
        return self.state if self.state.get("pack_id") == pack_id else None


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (None, 60.0),
        ("invalid", 60.0),
        ("nan", 60.0),
        ("15", 30.0),
        ("75", 75.0),
        ("600", 300.0),
    ],
)
def test_execution_activation_timeout_is_bounded(
    monkeypatch,
    configured,
    expected,
):
    if configured is None:
        monkeypatch.delenv(
            "MINDSCAPE_EXECUTION_ACTIVATION_TIMEOUT_SECONDS",
            raising=False,
        )
    else:
        monkeypatch.setenv(
            "MINDSCAPE_EXECUTION_ACTIVATION_TIMEOUT_SECONDS",
            configured,
        )

    assert capability_install_jobs._execution_activation_timeout_seconds() == expected


@pytest.mark.asyncio
async def test_execution_activation_client_uses_bounded_timeout(monkeypatch):
    observed = {}

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {"state": "activated", "manifest_hash": "hash-1"}

        @staticmethod
        def raise_for_status():
            return None

    class _Client:
        def __init__(self, *, timeout):
            observed["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, json):
            observed["url"] = url
            observed["json"] = json
            return _Response()

    import httpx

    monkeypatch.setenv("MINDSCAPE_EXECUTION_ACTIVATION_TIMEOUT_SECONDS", "75")
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    result = await CapabilityInstallJobService(
        store=object()
    )._notify_execution_activation(
        install_id="install-1",
        pipeline_payload={
            "capability_code": "yogacoach",
            "activation": {"manifest_hash": "hash-1"},
        },
    )

    assert observed["timeout"] == 75.0
    assert observed["json"]["manifest_hash"] == "hash-1"
    assert result["state"] == "activated"


@pytest.fixture(autouse=True)
def _no_committed_install_reconciliation(monkeypatch):
    monkeypatch.setattr(
        pack_install_reconciliation,
        "poll_install_reconciliation_once",
        lambda: None,
    )
    monkeypatch.setattr(
        executor,
        "require_runtime_database_mutation_allowed",
        lambda _operation, evidence=None: None,
    )


@pytest.mark.asyncio
async def test_install_job_enters_waiting_db_before_filesystem_promotion(monkeypatch):
    readiness = DatabaseWriteReadiness(
        ready=False,
        reason="postgres_recovery_in_progress",
        retry_after_seconds=17,
    )

    def fail_readiness(**_kwargs):
        raise DatabaseWriteNotReadyError(readiness)

    monkeypatch.setattr(
        executor,
        "wait_for_core_write_readiness",
        fail_readiness,
    )
    store = _FakeStore()
    service = CapabilityInstallJobService(store=store)

    result = await service.run_next_job(fastapi_app=object())

    assert result == {
        "install_id": "job-1",
        "state": "waiting_db",
        "reason": "postgres_recovery_in_progress",
        "retry_after_seconds": 17,
    }
    assert store.waiting == result


@pytest.mark.asyncio
async def test_install_job_persists_http_exception_detail(monkeypatch):
    def ready(**_kwargs):
        return None

    async def fail_pipeline(**_kwargs):
        raise HTTPException(
            status_code=400,
            detail={"error": "manifest_validation_failed", "field": "workspace_tools"},
        )

    monkeypatch.setattr(
        executor,
        "wait_for_core_write_readiness",
        ready,
    )
    monkeypatch.setattr(
        executor,
        "run_install_pipeline",
        fail_pipeline,
    )
    store = _FakeStore()
    service = CapabilityInstallJobService(store=store)

    result = await service.run_next_job(fastapi_app=object())

    assert result["state"] == "failed"
    assert "manifest_validation_failed" in result["error"]
    assert "workspace_tools" in result["error"]
    assert store.failed == result


def test_get_job_never_promotes_pending_from_a_registry_projection():
    result_payload = {
        "capability_code": "ig",
        "activation": {"manifest_hash": "hash-1"},
        "execution_activation": {"state": "pending_execution_activation"},
    }
    activation_state = {
        "pack_id": "ig",
        "install_state": "installed",
        "activation_state": "active",
        "activation_mode": "capability_registry_load",
        "manifest_hash": "hash-1",
        "updated_at": "2026-06-02T02:17:33Z",
    }
    store = _PendingActivationStore(result_payload)
    service = CapabilityInstallJobService(
        store=store,
        activation_service=_ActivationService(activation_state),
    )

    result = service.get_job("job-1")

    assert result["state"] == "pending_execution_activation"
    assert result["status_url"] == "/api/v1/capability-packs/install-jobs/job-1"
    assert store.succeeded_payload is None


def test_get_job_keeps_pending_activation_when_manifest_hash_differs():
    result_payload = {
        "capability_code": "ig",
        "activation": {"manifest_hash": "hash-1"},
        "execution_activation": {"state": "pending_execution_activation"},
    }
    activation_state = {
        "pack_id": "ig",
        "install_state": "installed",
        "activation_state": "active",
        "activation_mode": "capability_registry_load",
        "manifest_hash": "hash-2",
    }
    store = _PendingActivationStore(result_payload)
    service = CapabilityInstallJobService(
        store=store,
        activation_service=_ActivationService(activation_state),
    )

    result = service.get_job("job-1")

    assert result["state"] == "pending_execution_activation"
    assert result["status_url"] == "/api/v1/capability-packs/install-jobs/job-1"
    assert store.succeeded_payload is None


def test_get_job_normalizes_legacy_succeeded_payload_when_activation_is_active():
    result_payload = {
        "capability_code": "ig",
        "restart_required": True,
        "activation": {"manifest_hash": "hash-1"},
        "execution_activation": {"state": "activated"},
    }
    activation_state = {
        "pack_id": "ig",
        "install_state": "installed",
        "activation_state": "active",
        "activation_mode": "capability_registry_load",
        "manifest_hash": "hash-1",
    }
    store = _PendingActivationStore(result_payload)
    store.get_job = lambda _install_id: {
        "install_id": "job-1",
        "state": "succeeded",
        "result_payload": result_payload,
    }
    service = CapabilityInstallJobService(
        store=store,
        activation_service=_ActivationService(activation_state),
    )

    result = service.get_job("job-1")

    payload = result["result_payload"]
    assert payload["restart_required"] is False
    assert payload["backend_process_restart_required"] is False
    assert payload["runner_restart_required"] is False
    assert payload["execution_activation_state"] == "activated"


def test_get_job_keeps_legacy_restart_flag_when_activation_is_unavailable():
    result_payload = {
        "capability_code": "ig",
        "restart_required": True,
        "activation": {"manifest_hash": "hash-1"},
        "execution_activation": {"state": "activated"},
    }
    store = _PendingActivationStore(result_payload)
    store.get_job = lambda _install_id: {
        "install_id": "job-1",
        "state": "succeeded",
        "result_payload": result_payload,
    }
    service = CapabilityInstallJobService(
        store=store,
        activation_service=_ActivationService({"pack_id": "other"}),
    )

    result = service.get_job("job-1")

    payload = result["result_payload"]
    assert payload["restart_required"] is True
    assert "restart_decision" not in payload
