from app.services.artifact_lifecycle.policy import (
    ArtifactLifecycleCandidate,
    ArtifactLifecyclePolicy,
    is_active_status,
)


def _candidate(**overrides):
    base = {
        "artifact_id": "artifact-1",
        "workspace_id": "workspace-1",
        "task_id": "task-1",
        "execution_id": "exec-1",
        "storage_ref": "/workspace/artifacts/exec-1",
        "result_json_path": "/workspace/artifacts/exec-1/result.json",
        "checksum_sha256": "abc",
        "summary": "artifact summary",
        "manifest_summary": "manifest summary",
        "task_status": "succeeded",
    }
    base.update(overrides)
    return ArtifactLifecycleCandidate(**base)


def test_policy_removes_only_derived_summary_when_payload_is_safe():
    decision = ArtifactLifecyclePolicy().decide_summary_sidecar(
        _candidate(),
        summary_path_exists=True,
        result_json_exists=True,
        checksum_matches=True,
    )

    assert decision.action == "remove_summary"
    assert decision.reasons == ("derived-sidecar",)


def test_policy_blocks_active_tasks_and_missing_payloads():
    policy = ArtifactLifecyclePolicy()

    active = policy.decide_summary_sidecar(
        _candidate(task_status="running"),
        summary_path_exists=True,
        result_json_exists=True,
    )
    missing_result = policy.decide_summary_sidecar(
        _candidate(),
        summary_path_exists=True,
        result_json_exists=False,
    )

    assert active.action == "skip"
    assert active.reasons == ("active-task",)
    assert missing_result.action == "skip"
    assert missing_result.reasons == ("missing-result-json",)


def test_policy_blocks_missing_pointers_summary_and_checksum_mismatch():
    policy = ArtifactLifecyclePolicy()

    missing_pointer = policy.decide_summary_sidecar(
        _candidate(storage_ref=None, result_json_path=None),
        summary_path_exists=True,
        result_json_exists=True,
    )
    missing_summary = policy.decide_summary_sidecar(
        _candidate(summary=None, manifest_summary=None),
        summary_path_exists=True,
        result_json_exists=True,
    )
    checksum_mismatch = policy.decide_summary_sidecar(
        _candidate(),
        summary_path_exists=True,
        result_json_exists=True,
        checksum_matches=False,
    )

    assert missing_pointer.reasons == ("missing-db-pointer",)
    assert missing_summary.reasons == ("missing-db-summary",)
    assert checksum_mismatch.reasons == ("checksum-mismatch",)


def test_active_status_detection_keeps_terminal_statuses_available():
    assert is_active_status("pending") is True
    assert is_active_status("waiting_to_resume") is True
    assert is_active_status("succeeded") is False
    assert is_active_status("cancelled_by_user") is False
    assert is_active_status(None) is False
