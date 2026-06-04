from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "maintenance"
    / "reconcile_capability_install_activation_jobs.py"
)
SPEC = importlib.util.spec_from_file_location("activation_cleanup", SCRIPT_PATH)
activation_cleanup = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = activation_cleanup
SPEC.loader.exec_module(activation_cleanup)


def _job(
    *,
    pending_hash: str = "hash-old",
    state: str = activation_cleanup.PENDING_STATE,
    capability_code: str = "ig",
    updated_at: str = "2026-06-01T00:00:00+00:00",
):
    return activation_cleanup.PendingActivationJob(
        install_id="job-1",
        capability_code=capability_code,
        state=state,
        result_payload={
            "capability_code": capability_code,
            "version": "1.0.61",
            "activation": {"manifest_hash": pending_hash},
            "execution_activation": {"state": activation_cleanup.PENDING_STATE},
        },
        pending_manifest_hash=pending_hash,
        version="1.0.61",
        created_at="2026-06-01T00:00:00+00:00",
        updated_at=updated_at,
        error=None,
    )


def _activation(
    *,
    manifest_hash: str = "hash-active",
    install_state: str = "installed",
    activation_state: str = "active",
    updated_at: str = "2026-06-03T00:00:00+00:00",
):
    return activation_cleanup.ActivationSnapshot(
        pack_id="ig",
        install_state=install_state,
        activation_state=activation_state,
        manifest_hash=manifest_hash,
        updated_at=updated_at,
        version="1.0.88",
    )


def test_classifies_matching_hash_for_status_api_reconcile_only():
    decision = activation_cleanup.classify_pending_job(
        _job(pending_hash="hash-active"),
        _activation(manifest_hash="hash-active"),
    )

    assert decision.action == "reconcile_via_status_api"
    assert decision.apply_eligible is False
    assert decision.reason == "pending_hash_matches_active_hash"


def test_classifies_stale_hash_as_apply_eligible_superseded_failure():
    job = _job(pending_hash="hash-old")
    activation = _activation(manifest_hash="hash-active")

    decision = activation_cleanup.classify_pending_job(job, activation)
    payload = activation_cleanup.build_superseded_result_payload(
        job,
        activation,
        reconciled_at="2026-06-03T00:01:00+00:00",
    )

    assert decision.action == "stale_superseded_by_active_manifest"
    assert decision.apply_eligible is True
    assert decision.reason == activation_cleanup.STALE_REASON
    assert payload["execution_activation"]["state"] == "failed"
    assert payload["execution_activation"]["previous"] == {
        "state": activation_cleanup.PENDING_STATE
    }
    assert payload["maintenance_reconciliation"]["reason"] == activation_cleanup.STALE_REASON
    assert payload["superseded_by"] == {
        "pack_id": "ig",
        "version": "1.0.88",
        "manifest_hash": "hash-active",
        "activation_updated_at": "2026-06-03T00:00:00+00:00",
    }
    assert payload["restart_required"] is False
    assert payload["backend_process_restart_required"] is False
    assert payload["runner_restart_required"] is False


def test_blocks_when_activation_state_missing():
    decision = activation_cleanup.classify_pending_job(_job(), None)

    assert decision.action == "blocked_missing_active_state"
    assert decision.apply_eligible is False


def test_blocks_when_activation_is_not_active_installed():
    decision = activation_cleanup.classify_pending_job(
        _job(),
        _activation(install_state="installed", activation_state="pending_activation"),
    )

    assert decision.action == "blocked_activation_not_active"
    assert decision.apply_eligible is False


def test_blocks_when_active_state_is_older_than_pending_job():
    decision = activation_cleanup.classify_pending_job(
        _job(updated_at="2026-06-03T00:00:00+00:00"),
        _activation(updated_at="2026-06-01T00:00:00+00:00"),
    )

    assert decision.action == "blocked_active_state_older_than_job"
    assert decision.apply_eligible is False
