from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.maintenance import postgres_signal_observer_drill as drill_facade
from scripts.maintenance.postgres_signal_observer_core import (
    DisposableDrillSignalConfig,
    POSTGRES_BACKEND_PID_MAX,
    POSTGRES_SIGNAL_NAME,
    POSTGRES_SIGNAL_OUTPUT_BUDGET_BYTES,
    POSTGRES_SIGNAL_SENDER_EXECUTABLE,
    POSTGRES_SIGNAL_TERMINAL_DEADLINE_SECONDS,
    canonical_disposable_drill_name,
    canonical_observer_artifact_sha256,
    send_disposable_drill_signal,
)
from scripts.maintenance.postgres_signal_observer_core.artifact import (
    OBSERVER_SOURCE_PATHS,
)


DRILL_SUFFIX = "20260718T055442Z"
POSTGRES_IMAGE_REF = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE_REF = "mindscape-ai-local-core-backend@sha256:" + "c" * 64
TARGET_PID = 96


@pytest.fixture
def signal_config() -> DisposableDrillSignalConfig:
    return DisposableDrillSignalConfig(
        drill_suffix=DRILL_SUFFIX,
        postgres_image_ref=POSTGRES_IMAGE_REF,
        target_postgres_pid=TARGET_PID,
    )


def test_signal_sender_uses_one_exact_postgres_16_pg_ctl_argv(
    signal_config: DisposableDrillSignalConfig,
) -> None:
    argv = signal_config.docker_argv()

    assert argv == (
        "/usr/local/bin/docker",
        "exec",
        canonical_disposable_drill_name("postgres", DRILL_SUFFIX),
        "/usr/lib/postgresql/16/bin/pg_ctl",
        "kill",
        "QUIT",
        "96",
    )
    assert POSTGRES_SIGNAL_SENDER_EXECUTABLE == argv[3]
    assert POSTGRES_SIGNAL_NAME == argv[5]
    assert "sh" not in argv
    assert "-c" not in argv

    spec = signal_config.redacted_spec()
    assert spec["postgres_major"] == 16
    assert spec["shell"] is False
    assert spec["target_postgres_pid_disclosed"] is False
    assert spec["terminal_deadline_seconds"] == 10.0
    assert spec["output_budget_bytes"] == 4096
    assert "target_postgres_pid" not in spec
    assert "argv" not in spec


def test_postgres_image_build_contract_pins_pg_major_and_pg_ctl_executable() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    dockerfile = (repo_root / "docker/postgres/Dockerfile").read_text(encoding="utf-8")

    assert "ARG PG_MAJOR=16" in dockerfile
    assert 'test "${PG_MAJOR}" = "16"' in dockerfile
    assert 'test -x "/usr/lib/postgresql/${PG_MAJOR}/bin/pg_ctl"' in dockerfile
    assert "docker/postgres/Dockerfile" in OBSERVER_SOURCE_PATHS
    assert "scripts/maintenance/postgres_incident_gate.py" in OBSERVER_SOURCE_PATHS


def test_artifact_digest_changes_with_the_postgres_image_contract(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    mirror = tmp_path / "repo"
    for relative in OBSERVER_SOURCE_PATHS:
        source = repo_root / relative
        target = mirror / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    baseline = canonical_observer_artifact_sha256(mirror)
    dockerfile = mirror / "docker/postgres/Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8") + "\n# digest fixture\n",
        encoding="utf-8",
    )

    assert canonical_observer_artifact_sha256(mirror) != baseline


@pytest.mark.parametrize(
    "relative",
    (
        "backend/app/services/runtime_database_incident_gate.py",
        "backend/app/services/runtime_database_incident_core/evaluator.py",
        "backend/app/services/runtime_database_incident_core/journal.py",
        "backend/app/services/runtime_database_incident_core/models.py",
        "backend/app/services/runtime_database_incident_core/mutation_context.py",
    ),
)
def test_artifact_digest_binds_incident_admission_and_terminal_owners(
    tmp_path: Path,
    relative: str,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    mirror = tmp_path / "repo"
    for source_relative in OBSERVER_SOURCE_PATHS:
        source = repo_root / source_relative
        target = mirror / source_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    baseline = canonical_observer_artifact_sha256(mirror)
    owner = mirror / relative
    owner.write_bytes(owner.read_bytes() + b"\n# artifact owner fixture\n")

    assert canonical_observer_artifact_sha256(mirror) != baseline


@pytest.mark.parametrize(
    "relative",
    (
        "backend/app/services/runtime_database_incident_gate.py",
        "backend/app/services/runtime_database_incident_core/journal.py",
    ),
)
def test_artifact_digest_fails_closed_when_incident_owner_is_missing(
    tmp_path: Path,
    relative: str,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    mirror = tmp_path / "repo"
    for source_relative in OBSERVER_SOURCE_PATHS:
        source = repo_root / source_relative
        target = mirror / source_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    (mirror / relative).unlink()

    with pytest.raises(RuntimeError, match=f"observer_source_unavailable:{relative}"):
        canonical_observer_artifact_sha256(mirror)


@pytest.mark.parametrize(
    "pid",
    [0, -1, POSTGRES_BACKEND_PID_MAX + 1, True],
)
def test_signal_sender_rejects_unbounded_or_non_integer_pid(pid: object) -> None:
    config = DisposableDrillSignalConfig(
        drill_suffix=DRILL_SUFFIX,
        postgres_image_ref=POSTGRES_IMAGE_REF,
        target_postgres_pid=pid,  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="target_postgres_pid_invalid"):
        config.docker_argv()


def test_signal_sender_rejects_name_or_image_contract_drift() -> None:
    with pytest.raises(ValueError, match="disposable_drill_suffix_invalid"):
        DisposableDrillSignalConfig(
            drill_suffix="20260718t055442z",
            postgres_image_ref=POSTGRES_IMAGE_REF,
            target_postgres_pid=TARGET_PID,
        ).docker_argv()
    with pytest.raises(ValueError, match="postgres_drill_pg16_image_owner_mismatch"):
        DisposableDrillSignalConfig(
            drill_suffix=DRILL_SUFFIX,
            postgres_image_ref="unrelated-postgres:pg16@sha256:" + "b" * 64,
            target_postgres_pid=TARGET_PID,
        ).docker_argv()


def test_signal_sender_marks_sent_only_after_terminal_zero_and_redacts_output(
    signal_config: DisposableDrillSignalConfig,
) -> None:
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"sent\n", stderr=b"")

    receipt = send_disposable_drill_signal(signal_config, run=fake_run)
    serialized = json.dumps(receipt, sort_keys=True)

    assert len(calls) == 1
    assert tuple(calls[0][0]) == signal_config.docker_argv()
    assert calls[0][1] == {
        "check": False,
        "capture_output": True,
        "text": False,
        "timeout": POSTGRES_SIGNAL_TERMINAL_DEADLINE_SECONDS,
        "shell": False,
    }
    assert receipt["terminal"] is True
    assert receipt["terminal_exit_code"] == 0
    assert receipt["signal_sent"] is True
    assert receipt["first_failure"] is None
    assert receipt["target_postgres_pid"] == TARGET_PID
    assert receipt["stdout_sha256"] == hashlib.sha256(b"sent\n").hexdigest()
    assert receipt["output_disclosed"] is False
    assert "sent\\n" not in serialized


@pytest.mark.parametrize(
    ("outcome", "expected_failure", "terminal"),
    [
        (
            SimpleNamespace(returncode=7, stdout=b"", stderr=b"failed"),
            "disposable_drill_signal_sender_terminal_failure",
            True,
        ),
        (
            SimpleNamespace(returncode=None, stdout=b"", stderr=b""),
            "disposable_drill_signal_sender_result_invalid",
            True,
        ),
        (
            SimpleNamespace(
                returncode=0,
                stdout=b"x" * (POSTGRES_SIGNAL_OUTPUT_BUDGET_BYTES + 1),
                stderr=b"",
            ),
            "disposable_drill_signal_sender_output_budget_exceeded",
            True,
        ),
    ],
)
def test_signal_sender_terminal_failures_never_claim_signal_sent(
    signal_config: DisposableDrillSignalConfig,
    outcome: SimpleNamespace,
    expected_failure: str,
    terminal: bool,
) -> None:
    receipt = send_disposable_drill_signal(
        signal_config,
        run=lambda *_args, **_kwargs: outcome,
    )

    assert receipt["terminal"] is terminal
    assert receipt["signal_sent"] is False
    assert receipt["first_failure"] == expected_failure
    assert "failed" not in json.dumps(receipt, sort_keys=True)


def test_signal_sender_timeout_and_unavailable_are_bounded_and_redacted(
    signal_config: DisposableDrillSignalConfig,
) -> None:
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=signal_config.docker_argv(),
            timeout=POSTGRES_SIGNAL_TERMINAL_DEADLINE_SECONDS,
            output=b"partial",
            stderr=b"late",
        )

    timeout_receipt = send_disposable_drill_signal(signal_config, run=timeout)
    assert timeout_receipt["terminal"] is False
    assert timeout_receipt["signal_sent"] is False
    assert timeout_receipt["first_failure"] == (
        "disposable_drill_signal_sender_terminal_deadline_exceeded"
    )
    assert "partial" not in json.dumps(timeout_receipt, sort_keys=True)
    assert "late" not in json.dumps(timeout_receipt, sort_keys=True)

    unavailable_receipt = send_disposable_drill_signal(
        signal_config,
        run=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("secret")),
    )
    assert unavailable_receipt["terminal"] is False
    assert unavailable_receipt["signal_sent"] is False
    assert unavailable_receipt["first_failure"] == (
        "disposable_drill_signal_sender_unavailable"
    )
    assert "secret" not in json.dumps(unavailable_receipt, sort_keys=True)


def test_facade_print_spec_redacts_pid_and_send_requires_permit(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    exit_code = drill_facade.main(
        [
            "--print-signal-spec",
            "--drill-suffix",
            DRILL_SUFFIX,
            "--postgres-drill-image-ref",
            POSTGRES_IMAGE_REF,
            "--observer-backend-image-ref",
            OBSERVER_IMAGE_REF,
            "--target-postgres-pid",
            str(TARGET_PID),
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert payload["target_postgres_pid_disclosed"] is False
    assert "target_postgres_pid" not in payload
    assert "argv" not in payload

    with pytest.raises(
        SystemExit,
        match="formal_drill_full_sequence_entry_required",
    ):
        drill_facade.main(
            [
                "--send-synthetic-signal",
                "--journal-root",
                str(tmp_path),
                "--drill-suffix",
                DRILL_SUFFIX,
                "--postgres-drill-image-ref",
                POSTGRES_IMAGE_REF,
                "--observer-backend-image-ref",
                OBSERVER_IMAGE_REF,
                "--target-postgres-pid",
                str(TARGET_PID),
            ]
        )


def test_facade_and_core_expose_one_sender_without_fallback() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    facade_source = (
        repo_root / "scripts/maintenance/postgres_signal_observer_drill.py"
    ).read_text(encoding="utf-8")
    core_source = (
        repo_root / "scripts/maintenance/postgres_signal_observer_core/drill.py"
    ).read_text(encoding="utf-8")
    executor_source = (
        repo_root
        / "scripts/maintenance/postgres_signal_observer_core/drill_formal_executor.py"
    ).read_text(encoding="utf-8")
    combined = facade_source + core_source + executor_source

    assert "send_disposable_drill_signal" not in facade_source
    assert executor_source.count("send_disposable_drill_signal(") == 1
    assert core_source.count("def send_disposable_drill_signal(") == 1
    assert "docker kill" not in combined
    assert "os.kill" not in combined
    assert "shell=True" not in combined
    assert "/bin/sh" not in combined
    assert "fallback" not in combined.lower()
