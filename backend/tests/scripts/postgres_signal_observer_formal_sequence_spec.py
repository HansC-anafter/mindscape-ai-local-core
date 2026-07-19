from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.maintenance.postgres_signal_observer_core import (
    DRILL_APPLICATION_NAME,
    FORMAL_DRILL_SEQUENCE_ORDER,
    FORMAL_DRILL_TERMINAL_COMPLETE,
    DisposableDrillBootstrapConfig,
    DisposableDrillClientConfig,
    DisposableDrillObserverConfig,
    DisposableDrillSignalConfig,
    FormalDockerExecutionEnvelope,
    canonical_formal_drill_sequence,
    execute_formal_drill_sequence,
    materialize_formal_signal_envelope,
)
from scripts.maintenance.postgres_signal_observer_core.drill_escalation import (
    terminal_capture_metadata,
)
from scripts.maintenance.postgres_signal_observer_core.drill_readback import (
    CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS,
)
from scripts.maintenance.postgres_signal_observer_core.drill_readback_projection import (
    CONTAINER_READBACK_MAX_BYTES,
    CONTAINER_READBACK_SCHEMA_VERSION,
)


POSTGRES_IMAGE_REF = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE_REF = "mindscape-ai-local-core-backend@sha256:" + "b" * 64
DRILL_SUFFIX = "20260718T151758Z"


class _EqualToCaptureHashInput:
    def __eq__(self, other: object) -> bool:
        return other == "full_raw_subprocess_capture_bytes"


def _configs(tmp_path: Path) -> tuple[object, object, object, object]:
    repo_root = Path(__file__).resolve().parents[3]
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    bootstrap = DisposableDrillBootstrapConfig(
        drill_suffix=DRILL_SUFFIX,
        temp_root=Path(f"/private/tmp/mindscape-postgres-signal-drill-{DRILL_SUFFIX}"),
        postgres_image_ref=POSTGRES_IMAGE_REF,
    )
    observer = DisposableDrillObserverConfig(
        container_name=bootstrap.observer_container_name,
        pgbouncer_container_name=bootstrap.pgbouncer_container_name,
        observer_image_ref=OBSERVER_IMAGE_REF,
        journal_host_root=journal_root,
        repo_root=repo_root,
        artifact_sha256="c" * 64,
        source_commit="0123456789abcdef",
    )
    client = DisposableDrillClientConfig(
        container_name=bootstrap.client_container_name,
        network_name=bootstrap.network_name,
        postgres_image_ref=POSTGRES_IMAGE_REF,
        pgbouncer_host=bootstrap.pgbouncer_container_name,
        pgbouncer_port=6432,
        database_user="mindscape",
        database_name="mindscape_core",
        sleep_seconds=120,
    )
    signal = DisposableDrillSignalConfig(
        drill_suffix=DRILL_SUFFIX,
        postgres_image_ref=POSTGRES_IMAGE_REF,
        target_postgres_pid=42,
    )
    return bootstrap, observer, client, signal


def _docker_success(envelope: FormalDockerExecutionEnvelope) -> dict[str, object]:
    if envelope.result_kind == "identifier":
        return {"exit_code": 0, "output": "a" * 64}
    return {"exit_code": 0, "output": ""}


def _postflight(owner: str = "none", *, verified: bool = True) -> dict[str, object]:
    return {
        "remaining_resources_verified": verified,
        "terminal_owner": owner,
        "handed_back": owner == "none" and verified,
    }


def _gate(name: str, *, fail: str | None = None) -> dict[str, object]:
    passed = name != fail
    def terminal_zero() -> dict[str, object]:
        return {
            "status": "terminal_zero",
            "exit_code": 0,
            "terminal_capture": terminal_capture_metadata(b"", b"", exit_code=0),
        }

    if name == "pgbouncer_readiness":
        stages = {
            "container_readback": {
                "attempted": True,
                "attempt_count": 1,
                "success_count": 1,
                "passed": True,
                "last_result": {
                    "status": "validated",
                    "detail_code": None,
                    "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
                    "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
                    "terminal_deadline_seconds": (
                        CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
                    ),
                },
            },
            "pg_isready": {
                "attempted": True,
                "attempt_count": 1,
                "success_count": int(passed),
                "passed": passed,
                "last_result": (
                    terminal_zero()
                    if passed
                    else {
                        "status": "terminal_nonzero",
                        "exit_code": 3,
                        "terminal_capture": terminal_capture_metadata(
                            b"private-ready-output", b"private-ready-error", exit_code=3
                        ),
                    }
                ),
            },
            "show_version": {
                "attempted": passed,
                "attempt_count": int(passed),
                "success_count": int(passed),
                "passed": passed,
                "last_result": terminal_zero() if passed else None,
            },
        }
        return {
            "passed": passed,
            "gate": name,
            "detail_code": (
                None if passed else "formal_pgbouncer_pg_isready_failed"
            ),
            "startup_deadline_seconds": 10.0,
            "poll_seconds": 0.25,
            "stages": stages,
        }
    if name != "postgres_readiness":
        return {"passed": passed}

    stages = {
        "container_readback": {
            "attempted": True,
            "attempt_count": 1,
            "success_count": 1,
            "passed": True,
            "last_result": {
                "status": "validated",
                "detail_code": None,
                "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
                "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
                "terminal_deadline_seconds": (
                    CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
                ),
            },
        },
        "pg_isready": {
            "attempted": True,
            "attempt_count": 1,
            "success_count": int(passed),
            "passed": passed,
            "last_result": (
                terminal_zero()
                if passed
                else {
                    "status": "timeout",
                    "error_code": "formal_postgres_pg_isready_deadline_exceeded",
                }
            ),
        },
        "psql_select_one": {
            "attempted": passed,
            "attempt_count": int(passed),
            "success_count": int(passed),
            "passed": passed,
            "prior_terminal_attempt_index": None,
            "prior_terminal_result": None,
            "last_result": (
                terminal_zero() if passed else None
            ),
        },
    }
    return {
        "passed": passed,
        "gate": name,
        "detail_code": (
            None if passed else "formal_postgres_pg_isready_deadline_exceeded"
        ),
        "startup_deadline_seconds": 10.0,
        "poll_seconds": 0.25,
        "stages": stages,
    }


def _execute(configs: tuple[object, object, object, object], **callbacks: object):
    bootstrap, observer, client, signal = configs
    return execute_formal_drill_sequence(
        canonical_formal_drill_sequence(bootstrap, observer, client),
        materialize_operation=lambda owner: (
            materialize_formal_signal_envelope(signal)
            if owner == "source_owned_signal_sender"
            else (_ for _ in ()).throw(RuntimeError("unexpected operation"))
        ),
        **callbacks,
    )


def test_network_permission_failure_blocks_all_downstream_and_skips_docker_cleanup(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    revocations: list[str] = []

    def execute(envelope: FormalDockerExecutionEnvelope) -> dict[str, object]:
        calls.append(envelope.operation_class)
        return {
            "exit_code": 1,
            "output": "permission denied",
            "failure_code": "formal_isolated_network_create_permission_denied",
        }

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=execute,
        evaluate_gate=lambda name: (_ for _ in ()).throw(
            AssertionError(f"gate must not run: {name}")
        ),
        revoke_permit=revocations.append,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    assert calls == ["docker_create_disposable_isolated_network"]
    assert receipt["first_failure"] == (
        "formal_isolated_network_create_permission_denied"
    )
    assert revocations == [receipt["first_failure"]]
    assert receipt["downstream_operation_attempts"] == {
        "postgres": 0,
        "pgbouncer": 0,
        "observer": 0,
        "client": 0,
        "signal": 0,
    }
    assert receipt["cleanup_operation_attempts"] == 0
    assert receipt["same_permit_downstream_mutation_attempt"] is False
    assert receipt["validation_passed"] is False
    assert receipt["terminal_owner"] == "none"
    assert receipt["ownership_handed_back"] is True


def test_sequence_receipt_preserves_redacted_terminal_nonzero_capture_metadata(
    tmp_path: Path,
) -> None:
    stdout = b"network-create-denied"
    stderr = b"sensitive-daemon-detail"
    capture = {
        "terminal": True,
        "exit_code": 13,
        "stdout_present": True,
        "stdout_bytes": len(stdout),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_present": True,
        "stderr_bytes": len(stderr),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "captures_truncated": False,
        "hash_input": "full_raw_subprocess_capture_bytes",
        "output_disclosed": False,
    }

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=lambda _envelope: {
            "exit_code": 13,
            "output": "",
            "failure_code": "formal_isolated_network_create_permission_denied",
            "terminal_nonzero_capture": capture,
        },
        evaluate_gate=lambda name: (_ for _ in ()).throw(
            AssertionError(f"gate must not run: {name}")
        ),
        revoke_permit=lambda _reason: None,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    result = receipt["step_receipts"][0]["result"]
    assert result["exit_code"] == 13
    assert result["terminal_nonzero_capture"] == capture
    serialized = json.dumps(receipt, sort_keys=True)
    assert stdout.decode("ascii") not in serialized
    assert stderr.decode("ascii") not in serialized
    assert receipt["cleanup_operation_attempts"] == 0


def test_sequence_projects_exact_postgres_readiness_subreceipt_without_payload(
    tmp_path: Path,
) -> None:
    stdout = b"readiness-private-output"
    stderr = b"readiness-private-error"
    capture = {
        "terminal": True,
        "exit_code": 1,
        "stdout_present": True,
        "stdout_bytes": len(stdout),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_present": True,
        "stderr_bytes": len(stderr),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "captures_truncated": False,
        "hash_input": "full_raw_subprocess_capture_bytes",
        "output_disclosed": False,
        "unknown_capture_key": "must-drop",
    }
    gate = _gate("postgres_readiness", fail="postgres_readiness")
    gate["unknown_top_level"] = "must-drop"
    gate["stages"]["pg_isready"] = {
        "attempted": True,
        "attempt_count": 4,
        "success_count": 0,
        "passed": False,
        "last_result": {
            "status": "terminal_nonzero",
            "exit_code": 1,
            "terminal_capture": capture,
            "unknown_result_key": "must-drop",
        },
        "unknown_stage_key": "must-drop",
    }

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=_docker_success,
        evaluate_gate=lambda name: gate if name == "postgres_readiness" else _gate(name),
        revoke_permit=lambda _reason: None,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    projected = receipt["step_receipts"][2]
    assert projected["detail_code"] == "formal_postgres_pg_isready_deadline_exceeded"
    result = projected["stages"]["pg_isready"]["last_result"]
    assert result["terminal_capture"]["stdout_sha256"] == hashlib.sha256(
        stdout
    ).hexdigest()
    assert "unknown_top_level" not in projected
    assert "unknown_stage_key" not in projected["stages"]["pg_isready"]
    assert "unknown_result_key" not in result
    assert "unknown_capture_key" not in result["terminal_capture"]
    serialized = json.dumps(receipt, sort_keys=True)
    assert stdout.decode("ascii") not in serialized
    assert stderr.decode("ascii") not in serialized


def test_sequence_preserves_container_leaf_failure_and_terminal_cleanup(
    tmp_path: Path,
) -> None:
    gate = _gate("postgres_readiness", fail="postgres_readiness")
    gate["detail_code"] = "formal_postgres_container_readback_failed"
    gate["stages"]["container_readback"] = {
        "attempted": True,
        "attempt_count": 1,
        "success_count": 0,
        "passed": False,
        "last_result": {
            "status": "validation_failed",
            "detail_code": "formal_postgres_container_readback_failed",
            "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
            "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "leaf_failure_schema_version": 1,
            "leaf_failure_code": "postgres_container_readback_state_unready",
            "leaf_failure_count": 2,
            "leaf_failure_codes": [
                "postgres_container_readback_state_unready",
                "postgres_container_readback_health_mismatch",
            ],
            "raw_projection": {"Config.Env": ["POSTGRES_PASSWORD=sentinel"]},
            "inspect_argv": ["private-inspect-argv"],
        },
    }
    gate["stages"]["pg_isready"] = {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "last_result": None,
    }
    gate["stages"]["psql_select_one"] = {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "prior_terminal_attempt_index": None,
        "prior_terminal_result": None,
        "last_result": None,
    }
    revocations: list[str] = []

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=_docker_success,
        evaluate_gate=lambda name: gate if name == "postgres_readiness" else _gate(name),
        revoke_permit=revocations.append,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    projected = receipt["step_receipts"][2]
    leaf = projected["stages"]["container_readback"]["last_result"]
    assert leaf["leaf_failure_code"] == "postgres_container_readback_state_unready"
    assert leaf["leaf_failure_count"] == 2
    assert "raw_projection" not in leaf
    assert "inspect_argv" not in leaf
    assert "POSTGRES_PASSWORD=sentinel" not in json.dumps(receipt, sort_keys=True)
    assert receipt["first_failure"] == "formal_postgres_readiness_failed"
    assert revocations == ["formal_postgres_readiness_failed"]
    assert receipt["remaining_resources_verified"] is True
    assert receipt["ownership_handed_back"] is True
    assert receipt["validation_passed"] is False


def test_sequence_preserves_readback_terminal_nonzero_capture_and_cleanup(
    tmp_path: Path,
) -> None:
    stdout = b"private-readback-output\xff"
    stderr = b"private-readback-error\x80"
    capture = terminal_capture_metadata(stdout, stderr, exit_code=17)
    gate = _gate("postgres_readiness", fail="postgres_readiness")
    gate["detail_code"] = "formal_postgres_container_readback_failed"
    gate["stages"]["container_readback"] = {
        "attempted": True,
        "attempt_count": 1,
        "success_count": 0,
        "passed": False,
        "last_result": {
            "status": "validation_failed",
            "detail_code": "formal_postgres_container_readback_failed",
            "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
            "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "leaf_failure_schema_version": 1,
            "leaf_failure_code": "formal_postgres_readback_failed",
            "leaf_failure_count": 1,
            "leaf_failure_codes": ["formal_postgres_readback_failed"],
            "exit_code": 17,
            "terminal_nonzero_capture": capture,
            "raw_output": stdout,
        },
    }
    gate["stages"]["pg_isready"] = {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "last_result": None,
    }
    gate["stages"]["psql_select_one"] = {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "prior_terminal_attempt_index": None,
        "prior_terminal_result": None,
        "last_result": None,
    }
    revocations: list[str] = []

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=_docker_success,
        evaluate_gate=lambda name: gate if name == "postgres_readiness" else _gate(name),
        revoke_permit=revocations.append,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    result = receipt["step_receipts"][2]["stages"]["container_readback"][
        "last_result"
    ]
    assert result["exit_code"] == 17
    assert result["terminal_nonzero_capture"] == capture
    assert receipt["first_failure"] == "formal_postgres_readiness_failed"
    assert revocations == ["formal_postgres_readiness_failed"]
    assert receipt["downstream_operation_attempts"] == {
        "postgres": 1,
        "pgbouncer": 0,
        "observer": 0,
        "client": 0,
        "signal": 0,
    }
    assert receipt["remaining_resources_verified"] is True
    assert receipt["ownership_handed_back"] is True
    serialized = json.dumps(receipt, sort_keys=True)
    assert "private-readback-output" not in serialized
    assert "private-readback-error" not in serialized


@pytest.mark.parametrize(
    "invalid_kind",
    [
        "capture_hash",
        "capture_empty_hash",
        "capture_hash_input_type",
        "mixed_failure_leaves",
    ],
)
def test_sequence_rejects_malformed_readback_capture_without_downstream(
    tmp_path: Path,
    invalid_kind: str,
) -> None:
    capture = terminal_capture_metadata(b"private", b"error", exit_code=17)
    if invalid_kind == "capture_hash":
        capture["stdout_sha256"] = "invalid"
    if invalid_kind == "capture_empty_hash":
        capture["stdout_present"] = False
        capture["stdout_bytes"] = 0
        capture["stdout_sha256"] = "0" * 64
    if invalid_kind == "capture_hash_input_type":
        capture["hash_input"] = _EqualToCaptureHashInput()
    failure_codes = ["formal_postgres_readback_failed"]
    if invalid_kind == "mixed_failure_leaves":
        failure_codes.append("formal_postgres_readback_projection_invalid")
    gate = _gate("postgres_readiness", fail="postgres_readiness")
    gate["detail_code"] = "formal_postgres_container_readback_failed"
    gate["stages"]["container_readback"] = {
        "attempted": True,
        "attempt_count": 1,
        "success_count": 0,
        "passed": False,
        "last_result": {
            "status": "validation_failed",
            "detail_code": "formal_postgres_container_readback_failed",
            "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
            "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "leaf_failure_schema_version": 1,
            "leaf_failure_code": "formal_postgres_readback_failed",
            "leaf_failure_count": len(failure_codes),
            "leaf_failure_codes": failure_codes,
            "exit_code": 17,
            "terminal_nonzero_capture": capture,
        },
    }
    gate["stages"]["pg_isready"] = {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "last_result": None,
    }
    gate["stages"]["psql_select_one"] = {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "prior_terminal_attempt_index": None,
        "prior_terminal_result": None,
        "last_result": None,
    }
    revocations: list[str] = []

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=_docker_success,
        evaluate_gate=lambda name: gate if name == "postgres_readiness" else _gate(name),
        revoke_permit=revocations.append,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    assert receipt["step_receipts"][2] == {
        "name": "postgres_readiness",
        "kind": "gate",
        "passed": False,
        "detail_code": "formal_postgres_readiness_receipt_invalid",
    }
    assert receipt["first_failure"] == "formal_postgres_readiness_failed"
    assert revocations == ["formal_postgres_readiness_failed"]
    assert receipt["downstream_operation_attempts"] == {
        "postgres": 1,
        "pgbouncer": 0,
        "observer": 0,
        "client": 0,
        "signal": 0,
    }
    assert receipt["remaining_resources_verified"] is True
    assert receipt["ownership_handed_back"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_status",
        "wrong_index",
        "stale_index",
        "missing_prior",
        "extra_key",
        "bad_hash",
    ],
)
def test_sequence_rejects_malformed_prior_psql_result_and_cleans_up(
    tmp_path: Path,
    mutation: str,
) -> None:
    gate = _gate("postgres_readiness")
    gate["passed"] = False
    gate["detail_code"] = "formal_postgres_psql_select_one_deadline_exceeded"
    gate["stages"]["pg_isready"].update(
        {"attempt_count": 2, "success_count": 2, "passed": True}
    )
    psql = gate["stages"]["psql_select_one"]
    psql.update(
        {
            "attempt_count": 2,
            "success_count": 0,
            "passed": False,
            "last_result": {
                "status": "timeout",
                "error_code": "formal_postgres_psql_select_one_deadline_exceeded",
            },
            "prior_terminal_attempt_index": 1,
            "prior_terminal_result": {
                "status": "terminal_nonzero",
                "exit_code": 2,
                "terminal_capture": terminal_capture_metadata(
                    b"private", b"secret", exit_code=2
                ),
            },
        }
    )
    if mutation == "wrong_status":
        psql["prior_terminal_result"] = {
            "status": "timeout",
            "error_code": "formal_postgres_psql_select_one_deadline_exceeded",
        }
    elif mutation == "wrong_index":
        psql["prior_terminal_attempt_index"] = True
    elif mutation == "stale_index":
        gate["stages"]["pg_isready"].update(
            {"attempt_count": 3, "success_count": 3}
        )
        psql["attempt_count"] = 3
        psql["prior_terminal_attempt_index"] = 1
    elif mutation == "missing_prior":
        psql["prior_terminal_attempt_index"] = None
        psql["prior_terminal_result"] = None
    elif mutation == "extra_key":
        psql["prior_terminal_result"]["raw_output"] = "secret"
    else:
        psql["prior_terminal_result"]["terminal_capture"]["stdout_sha256"] = "bad"
    revocations: list[str] = []

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=_docker_success,
        evaluate_gate=lambda name: gate if name == "postgres_readiness" else _gate(name),
        revoke_permit=revocations.append,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    assert receipt["step_receipts"][2]["detail_code"] == (
        "formal_postgres_readiness_receipt_invalid"
    )
    assert receipt["first_failure"] == "formal_postgres_readiness_failed"
    assert revocations == ["formal_postgres_readiness_failed"]
    assert receipt["downstream_operation_attempts"]["pgbouncer"] == 0
    assert receipt["remaining_resources_verified"] is True
    assert receipt["ownership_handed_back"] is True


def test_sequence_rejects_forged_readiness_success_and_capture_shape(
    tmp_path: Path,
) -> None:
    forged_success = _gate("postgres_readiness")
    forged_success["passed"] = False
    forged_success["detail_code"] = "formal_postgres_psql_select_one_deadline_exceeded"

    invalid_capture = _gate("postgres_readiness", fail="postgres_readiness")
    pg_capture = terminal_capture_metadata(b"private", b"", exit_code=1)
    pg_capture["stdout_present"] = False
    invalid_capture["stages"]["pg_isready"] = {
        "attempted": True,
        "attempt_count": 1,
        "success_count": 0,
        "passed": False,
        "last_result": {
            "status": "terminal_nonzero",
            "exit_code": 1,
            "terminal_capture": pg_capture,
        },
    }

    invalid_pg_success = _gate("postgres_readiness")
    invalid_pg_success["stages"]["pg_isready"]["last_result"] = {
        "status": "result_invalid",
        "error_code": "formal_postgres_readiness_capture_invalid",
    }

    mismatched_container_detail = _gate(
        "postgres_readiness", fail="postgres_readiness"
    )
    mismatched_container_detail["detail_code"] = (
        "formal_postgres_container_readback_failed"
    )

    unhashable_detail = _gate("postgres_readiness", fail="postgres_readiness")
    unhashable_detail["detail_code"] = []

    unhashable_status = _gate("postgres_readiness", fail="postgres_readiness")
    unhashable_status["stages"]["pg_isready"]["last_result"]["status"] = []

    unhashable_error = _gate("postgres_readiness", fail="postgres_readiness")
    unhashable_error["stages"]["pg_isready"]["last_result"]["error_code"] = []

    non_string_sha = _gate("postgres_readiness")
    non_string_sha["stages"]["pg_isready"]["last_result"]["terminal_capture"][
        "stdout_sha256"
    ] = int("1" * 64)

    zero_without_success = _gate("postgres_readiness")
    zero_without_success["passed"] = False
    zero_without_success["detail_code"] = (
        "formal_postgres_psql_select_one_deadline_exceeded"
    )
    zero_without_success["stages"]["psql_select_one"]["success_count"] = 0
    zero_without_success["stages"]["psql_select_one"]["passed"] = False

    invalid_last_result_after_success = _gate(
        "postgres_readiness", fail="postgres_readiness"
    )
    invalid_last_result_after_success["stages"]["pg_isready"][
        "success_count"
    ] = 1
    invalid_last_result_after_success["stages"]["pg_isready"]["passed"] = True
    invalid_last_result_after_success["stages"]["pg_isready"]["last_result"] = {
        "status": "result_invalid",
        "error_code": "formal_postgres_readiness_capture_invalid",
    }

    unallowlisted_container_leaf = _gate(
        "postgres_readiness", fail="postgres_readiness"
    )
    unallowlisted_container_leaf["detail_code"] = (
        "formal_postgres_container_readback_failed"
    )
    unallowlisted_container_leaf["stages"]["container_readback"] = {
        "attempted": True,
        "attempt_count": 1,
        "success_count": 0,
        "passed": False,
        "last_result": {
            "status": "validation_failed",
            "detail_code": "formal_postgres_container_readback_failed",
            "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
            "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "leaf_failure_schema_version": 1,
            "leaf_failure_code": "private-unallowlisted-code",
            "leaf_failure_count": 1,
            "leaf_failure_codes": ["private-unallowlisted-code"],
        },
    }
    unallowlisted_container_leaf["stages"]["pg_isready"] = {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "last_result": None,
    }

    contradictory_container_leaf_count = _gate(
        "postgres_readiness", fail="postgres_readiness"
    )
    contradictory_container_leaf_count["detail_code"] = (
        "formal_postgres_container_readback_failed"
    )
    contradictory_container_leaf_count["stages"]["container_readback"] = {
        "attempted": True,
        "attempt_count": 1,
        "success_count": 0,
        "passed": False,
        "last_result": {
            "status": "validation_failed",
            "detail_code": "formal_postgres_container_readback_failed",
            "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
            "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "leaf_failure_schema_version": 1,
            "leaf_failure_code": "postgres_container_readback_state_unready",
            "leaf_failure_count": 2,
            "leaf_failure_codes": ["postgres_container_readback_state_unready"],
        },
    }
    contradictory_container_leaf_count["stages"]["pg_isready"] = {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "last_result": None,
    }

    boolean_container_leaf_schema = _gate(
        "postgres_readiness", fail="postgres_readiness"
    )
    boolean_container_leaf_schema["detail_code"] = (
        "formal_postgres_container_readback_failed"
    )
    boolean_container_leaf_schema["stages"]["container_readback"] = {
        **contradictory_container_leaf_count["stages"]["container_readback"],
        "last_result": {
            **contradictory_container_leaf_count["stages"]["container_readback"][
                "last_result"
            ],
            "leaf_failure_schema_version": True,
            "leaf_failure_count": 1,
        },
    }
    boolean_container_leaf_schema["stages"]["pg_isready"] = {
        **contradictory_container_leaf_count["stages"]["pg_isready"]
    }

    boolean_container_leaf_count = _gate(
        "postgres_readiness", fail="postgres_readiness"
    )
    boolean_container_leaf_count["detail_code"] = (
        "formal_postgres_container_readback_failed"
    )
    boolean_container_leaf_count["stages"]["container_readback"] = {
        **boolean_container_leaf_schema["stages"]["container_readback"],
        "last_result": {
            **boolean_container_leaf_schema["stages"]["container_readback"][
                "last_result"
            ],
            "leaf_failure_schema_version": 1,
            "leaf_failure_count": True,
        },
    }
    boolean_container_leaf_count["stages"]["pg_isready"] = {
        **contradictory_container_leaf_count["stages"]["pg_isready"]
    }

    for index, gate in enumerate(
        (
            forged_success,
            invalid_capture,
            invalid_pg_success,
            mismatched_container_detail,
            unhashable_detail,
            unhashable_status,
            unhashable_error,
            non_string_sha,
            zero_without_success,
            invalid_last_result_after_success,
            unallowlisted_container_leaf,
            contradictory_container_leaf_count,
            boolean_container_leaf_schema,
            boolean_container_leaf_count,
        )
    ):
        case_root = tmp_path / str(index)
        case_root.mkdir()
        revocations: list[str] = []
        receipt = _execute(
            _configs(case_root),
            execute_docker=_docker_success,
            evaluate_gate=(
                lambda name, source=gate: source
                if name == "postgres_readiness"
                else _gate(name)
            ),
            revoke_permit=revocations.append,
            finalize_cleanup=lambda _failure: _postflight(),
        )
        projected = receipt["step_receipts"][2]
        assert projected == {
            "name": "postgres_readiness",
            "kind": "gate",
            "passed": False,
            "detail_code": "formal_postgres_readiness_receipt_invalid",
        }
        assert receipt["first_failure"] == "formal_postgres_readiness_failed"
        assert revocations == ["formal_postgres_readiness_failed"]
        assert receipt["remaining_resources_verified"] is True
        assert receipt["ownership_handed_back"] is True
        assert receipt["validation_passed"] is False


def test_readiness_failure_uses_same_latch_and_blocks_later_mutations(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def execute(envelope: FormalDockerExecutionEnvelope) -> dict[str, object]:
        calls.append(envelope.operation_class)
        return _docker_success(envelope)

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=execute,
        evaluate_gate=lambda name: _gate(name, fail="postgres_readiness"),
        revoke_permit=lambda _reason: None,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    assert receipt["first_failure"] == "formal_postgres_readiness_failed"
    assert receipt["attempted_steps"] == [
        "network_create",
        "postgres_bootstrap",
        "postgres_readiness",
    ]
    assert receipt["downstream_operation_attempts"]["pgbouncer"] == 0
    assert receipt["downstream_operation_attempts"]["observer"] == 0
    assert receipt["downstream_operation_attempts"]["client"] == 0
    assert receipt["downstream_operation_attempts"]["signal"] == 0
    assert calls[-3:] == [
        "docker_stop_disposable_isolated_postgresql",
        "docker_remove_disposable_isolated_postgresql",
        "docker_remove_disposable_isolated_network",
    ]
    assert receipt["validation_passed"] is False


def test_exit_zero_invalid_identifier_runs_exact_may_exist_cleanup(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def execute(envelope: FormalDockerExecutionEnvelope) -> dict[str, object]:
        calls.append(envelope.operation_class)
        if envelope.operation_class == "docker_create_disposable_isolated_network":
            return {"exit_code": 0, "output": "invalid-identifier"}
        return {"exit_code": 0, "output": ""}

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=execute,
        evaluate_gate=_gate,
        revoke_permit=lambda _reason: None,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    assert calls == [
        "docker_create_disposable_isolated_network",
        "docker_remove_disposable_isolated_network",
    ]
    assert receipt["cleanup_operation_attempts"] == 1
    assert receipt["downstream_operation_attempts"] == {
        "postgres": 0,
        "pgbouncer": 0,
        "observer": 0,
        "client": 0,
        "signal": 0,
    }
    assert receipt["validation_passed"] is False


def test_observer_health_failure_cleans_started_observer_and_blocks_client(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def execute(envelope: FormalDockerExecutionEnvelope) -> dict[str, object]:
        calls.append(envelope.operation_class)
        return _docker_success(envelope)

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=execute,
        evaluate_gate=lambda name: _gate(name, fail="observer_health"),
        revoke_permit=lambda _reason: None,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    assert receipt["first_failure"] == "formal_observer_health_failed"
    assert "docker_run_disposable_isolated_client" not in calls
    assert calls[-7:] == [
        "docker_stop_disposable_isolated_observer",
        "docker_remove_disposable_isolated_observer",
        "docker_stop_disposable_isolated_pgbouncer",
        "docker_remove_disposable_isolated_pgbouncer",
        "docker_stop_disposable_isolated_postgresql",
        "docker_remove_disposable_isolated_postgresql",
        "docker_remove_disposable_isolated_network",
    ]


def test_success_requires_every_gate_correlation_revocation_cleanup_and_handback(
    tmp_path: Path,
) -> None:
    terminal_reasons: list[str] = []

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=_docker_success,
        evaluate_gate=_gate,
        revoke_permit=terminal_reasons.append,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    assert receipt["attempted_steps"] == list(FORMAL_DRILL_SEQUENCE_ORDER)
    assert receipt["first_failure"] is None
    assert receipt["correlation_passed"] is True
    assert terminal_reasons == [FORMAL_DRILL_TERMINAL_COMPLETE]
    assert receipt["permit_revocation_completed"] is True
    assert receipt["cleanup_operation_attempts"] == 9
    assert receipt["remaining_resources_verified"] is True
    assert receipt["terminal_owner"] == "none"
    assert receipt["ownership_handed_back"] is True
    assert receipt["validation_passed"] is True


def test_correlation_failure_cannot_claim_validation(tmp_path: Path) -> None:
    receipt = _execute(
        _configs(tmp_path),
        execute_docker=_docker_success,
        evaluate_gate=lambda name: _gate(name, fail="sender_target_correlation"),
        revoke_permit=lambda _reason: None,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    assert receipt["first_failure"] == "formal_sender_target_correlation_failed"
    assert receipt["correlation_passed"] is False
    assert receipt["validation_passed"] is False


def test_revocation_or_cleanup_failure_never_forges_owner_handback(
    tmp_path: Path,
) -> None:
    def execute(envelope: FormalDockerExecutionEnvelope) -> dict[str, object]:
        if envelope.operation_class == "docker_stop_disposable_isolated_client":
            return {"exit_code": 1, "output": "cleanup failure"}
        return _docker_success(envelope)

    receipt = _execute(
        _configs(tmp_path),
        execute_docker=execute,
        evaluate_gate=_gate,
        revoke_permit=lambda _reason: (_ for _ in ()).throw(
            RuntimeError("revocation failure")
        ),
        finalize_cleanup=lambda _failure: _postflight(
            "runtime-db-incident-owner", verified=False
        ),
    )

    assert receipt["first_failure"] is None
    assert receipt["permit_revocation_completed"] is False
    assert receipt["cleanup_completed"] is False
    assert receipt["validation_passed"] is False
    assert receipt["terminal_owner"] == "runtime-db-incident-owner"
    assert receipt["ownership_handed_back"] is False


def test_facade_factory_owns_exact_sequence_and_rejects_manual_identity_drift(
    tmp_path: Path,
) -> None:
    configs = _configs(tmp_path)
    definition = canonical_formal_drill_sequence(*configs[:3])
    spec = definition.redacted_spec()

    assert spec["entry"] == (
        "postgres_signal_observer_drill.execute_formal_drill_sequence"
    )
    assert spec["manual_formal_mutation_steps_allowed"] is False
    assert [item["name"] for item in spec["sequence"]] == list(
        FORMAL_DRILL_SEQUENCE_ORDER
    )
    assert all(
        item["operation"] is None
        or item["operation"].get("source_owned_late_bound") is True
        or item["operation"]["argv"][0] == "/usr/local/bin/docker"
        for item in spec["sequence"]
    )
    assert all(
        item["operation"] is None
        or item["operation"].get("source_owned_late_bound") is True
        or item["operation"]["shell"] is False
        for item in spec["sequence"]
    )
    assert f"PGAPPNAME={DRILL_APPLICATION_NAME}" in configs[2].docker_argv()

    drifted_client = DisposableDrillClientConfig(
        **{**configs[2].__dict__, "network_name": "wrong-network"}
    )
    try:
        canonical_formal_drill_sequence(configs[0], configs[1], drifted_client)
    except ValueError as exc:
        assert str(exc) == "formal_drill_sequence_identity_mismatch"
    else:
        raise AssertionError("caller-owned sequence identity must fail closed")


def test_signal_envelope_is_materialized_from_exact_source_owned_pid(
    tmp_path: Path,
) -> None:
    configs = list(_configs(tmp_path))
    configs[3] = DisposableDrillSignalConfig(
        drill_suffix=DRILL_SUFFIX,
        postgres_image_ref=POSTGRES_IMAGE_REF,
        target_postgres_pid=4242,
    )
    executed: list[FormalDockerExecutionEnvelope] = []

    def execute(envelope: FormalDockerExecutionEnvelope) -> dict[str, object]:
        executed.append(envelope)
        return _docker_success(envelope)

    receipt = _execute(
        tuple(configs),
        execute_docker=execute,
        evaluate_gate=_gate,
        revoke_permit=lambda _reason: None,
        finalize_cleanup=lambda _failure: _postflight(),
    )
    signal_envelope = next(
        item
        for item in executed
        if item.operation_class == "docker_exec_disposable_isolated_signal_sender"
    )
    signal_step = next(
        item for item in receipt["step_receipts"] if item["name"] == "signal_send"
    )
    assert signal_envelope.argv[-1] == "4242"
    assert signal_step["operation"]["argv"] == list(signal_envelope.argv)
    assert signal_step["operation"]["argv_sha256"] == hashlib.sha256(
        "\0".join(signal_envelope.argv).encode("utf-8")
    ).hexdigest()
    definition_spec = canonical_formal_drill_sequence(*configs[:3]).redacted_spec()
    declared_signal = next(
        item for item in definition_spec["sequence"] if item["name"] == "signal_send"
    )
    assert declared_signal["operation"]["source_owned_late_bound"] is True
    assert "argv" not in declared_signal["operation"]


def test_sequence_projects_pgbouncer_readiness_and_fails_malformed_capture_closed(
    tmp_path: Path,
) -> None:
    revocations: list[str] = []
    configs = _configs(tmp_path)
    failed_gate = _gate("pgbouncer_readiness", fail="pgbouncer_readiness")
    receipt = _execute(
        configs,
        execute_docker=_docker_success,
        evaluate_gate=lambda name: (
            failed_gate if name == "pgbouncer_readiness" else _gate(name)
        ),
        revoke_permit=revocations.append,
        finalize_cleanup=lambda _failure: _postflight(),
    )

    projected = next(
        item
        for item in receipt["step_receipts"]
        if item["name"] == "pgbouncer_readiness"
    )
    assert projected["detail_code"] == "formal_pgbouncer_pg_isready_failed"
    assert projected["stages"]["show_version"]["attempt_count"] == 0
    assert projected["stages"]["pg_isready"]["last_result"]["exit_code"] == 3
    assert "private-ready" not in json.dumps(receipt, sort_keys=True)
    assert receipt["first_failure"] == "formal_pgbouncer_readiness_failed"
    assert revocations == ["formal_pgbouncer_readiness_failed"]
    assert receipt["cleanup_operation_attempts"] == 5
    assert receipt["ownership_handed_back"] is True

    failed_gate["stages"]["pg_isready"]["last_result"][
        "terminal_capture"
    ]["stdout_sha256"] = "Z" * 64
    malformed = _execute(
        configs,
        execute_docker=_docker_success,
        evaluate_gate=lambda name: (
            failed_gate if name == "pgbouncer_readiness" else _gate(name)
        ),
        revoke_permit=lambda _reason: None,
        finalize_cleanup=lambda _failure: _postflight(),
    )
    invalid = next(
        item
        for item in malformed["step_receipts"]
        if item["name"] == "pgbouncer_readiness"
    )
    assert invalid == {
        "name": "pgbouncer_readiness",
        "kind": "gate",
        "passed": False,
        "detail_code": "formal_pgbouncer_readiness_receipt_invalid",
    }
    assert malformed["first_failure"] == "formal_pgbouncer_readiness_failed"
    assert malformed["cleanup_operation_attempts"] == 5
    assert malformed["ownership_handed_back"] is True

    failed_gate["stages"]["container_readback"]["last_result"]["role"] = "postgres"
    wrong_role = _execute(
        configs,
        execute_docker=_docker_success,
        evaluate_gate=lambda name: (
            failed_gate if name == "pgbouncer_readiness" else _gate(name)
        ),
        revoke_permit=lambda _reason: None,
        finalize_cleanup=lambda _failure: _postflight(),
    )
    invalid_role = next(
        item
        for item in wrong_role["step_receipts"]
        if item["name"] == "pgbouncer_readiness"
    )
    assert invalid_role["detail_code"] == "formal_pgbouncer_readiness_receipt_invalid"
    assert wrong_role["first_failure"] == "formal_pgbouncer_readiness_failed"
    assert wrong_role["cleanup_operation_attempts"] == 5
    assert wrong_role["ownership_handed_back"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        "startup_budget",
        "poll_budget",
        "attempt_bound",
        "show_without_pg_success",
    ],
)
def test_sequence_rejects_pgbouncer_shared_deadline_contract_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    configs = _configs(tmp_path)
    gate = json.loads(json.dumps(_gate("pgbouncer_readiness")))
    if mutation == "startup_budget":
        gate["startup_deadline_seconds"] = 9.0
    elif mutation == "poll_budget":
        gate["poll_seconds"] = 0.5
    elif mutation == "attempt_bound":
        stage = gate["stages"]["pg_isready"]
        stage["attempt_count"] = 41
        stage["success_count"] = 1
    else:
        gate["passed"] = False
        gate["detail_code"] = "formal_pgbouncer_show_version_failed"
        gate["stages"]["pg_isready"] = {
            "attempted": True,
            "attempt_count": 1,
            "success_count": 0,
            "passed": False,
            "last_result": {
                "status": "terminal_nonzero",
                "exit_code": 2,
                "terminal_capture": terminal_capture_metadata(
                    b"secret-sentinel-output", b"", exit_code=2
                ),
            },
        }
    receipt = _execute(
        configs,
        execute_docker=_docker_success,
        evaluate_gate=lambda name: gate if name == "pgbouncer_readiness" else _gate(name),
        revoke_permit=lambda _reason: None,
        finalize_cleanup=lambda _failure: _postflight(),
    )
    projected = next(
        item
        for item in receipt["step_receipts"]
        if item["name"] == "pgbouncer_readiness"
    )
    assert projected["detail_code"] == "formal_pgbouncer_readiness_receipt_invalid"
    assert receipt["first_failure"] == "formal_pgbouncer_readiness_failed"
    assert receipt["cleanup_operation_attempts"] == 5
    assert receipt["ownership_handed_back"] is True
    assert "secret-sentinel-output" not in json.dumps(receipt, sort_keys=True)
