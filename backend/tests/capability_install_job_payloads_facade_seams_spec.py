from types import SimpleNamespace

from backend.app.routes.core.capability_install_core.restart_policy import (
    INSTALL_RESTART_SEMANTICS_VERSION,
)
from backend.app.services import capability_install_jobs
from backend.app.services.capability_install_job_payloads import (
    _pipeline_result_to_payload,
    _status_url,
)


def test_capability_install_jobs_reexports_status_and_payload_helpers() -> None:
    assert capability_install_jobs._status_url is _status_url
    assert capability_install_jobs._pipeline_result_to_payload is _pipeline_result_to_payload
    assert _status_url("job-123") == "/api/v1/capability-packs/install-jobs/job-123"


def test_pipeline_result_to_payload_applies_restart_decision_without_live_job() -> None:
    result = SimpleNamespace(
        success=True,
        capability_code="demo_pack",
        version="1.2.3",
        warnings=["warn"],
        restart_required=True,
        restart_triggered=False,
        hot_reload_result={"performed": False},
        webhook_result={"sent": False},
        activation={"manifest_hash": "hash-1"},
        validation={"state": "passed"},
        pack_metadata={"title": "Demo"},
        restart_decision={
            "execution_activation_required": True,
            "execution_activation_state": "pending_execution_activation",
            "backend_process_restart_required": False,
            "runner_restart_required": False,
            "restart_webhook_required": False,
            "legacy_restart_required": False,
            "reasons": ["pack_install_requires_execution_activation"],
            "semantic_version": INSTALL_RESTART_SEMANTICS_VERSION,
        },
    )

    payload = _pipeline_result_to_payload(result)

    assert payload["success"] is True
    assert payload["capability_code"] == "demo_pack"
    assert payload["version"] == "1.2.3"
    assert payload["warnings"] == ["warn"]
    assert payload["restart_required"] is False
    assert payload["backend_process_restart_required"] is False
    assert payload["runner_restart_required"] is False
    assert payload["execution_activation_required"] is True
    assert payload["execution_activation_state"] == "pending_execution_activation"
    assert payload["restart_semantics_version"] == INSTALL_RESTART_SEMANTICS_VERSION
    assert payload["hot_reload"] == {"performed": False}
    assert payload["webhook"] == {"sent": False}
    assert payload["activation"] == {"manifest_hash": "hash-1"}
    assert payload["validation"] == {"state": "passed"}
    assert payload["pack_metadata"] == {"title": "Demo"}
