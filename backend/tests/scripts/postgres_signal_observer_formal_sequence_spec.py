from __future__ import annotations

import hashlib
import json
from pathlib import Path

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


POSTGRES_IMAGE_REF = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE_REF = "mindscape-ai-local-core-backend@sha256:" + "b" * 64
DRILL_SUFFIX = "20260718T151758Z"


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
        evaluate_gate=lambda name: {"passed": name != "postgres_readiness"},
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
        evaluate_gate=lambda _name: {"passed": True},
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
        evaluate_gate=lambda name: {"passed": name != "observer_health"},
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
        evaluate_gate=lambda _name: {"passed": True},
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
        evaluate_gate=lambda name: {"passed": name != "sender_target_correlation"},
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
        evaluate_gate=lambda _name: {"passed": True},
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
        evaluate_gate=lambda _name: {"passed": True},
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
