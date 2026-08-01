from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.services.runtime_database_incident_gate import (
    IncidentDiagnosticPermit,
    RuntimeDatabaseIncidentJournal,
)
from scripts.maintenance.postgres_signal_observer_core import (
    EvidenceCapacityExhausted,
    ObserverConfig,
    ObserverEvidenceStore,
    PgBouncerCorrelationClient,
    PostgresSignalObserver,
    TraceFsInstance,
    canonical_observer_artifact_sha256,
    parse_signal_generate_line,
    read_namespace_pids,
)
from scripts.maintenance.postgres_signal_observer_core.pgbouncer import (
    validate_pgbouncer_correlation,
)
from scripts.maintenance.postgres_signal_observer import (
    _healthcheck,
    _write_startup_health,
)


TRACE_LINE = (
    "postgres-sender-4210  [003] .... 12345.678901: signal_generate: "
    "sig=3 errno=0 code=0 comm=postgres pid=54909 grp=0 res=0"
)
POSTMASTER_FANOUT_TRACE_LINE = TRACE_LINE.replace("postgres-sender", "postgres")


def test_parses_exact_sigquit_sender_and_rejects_malformed_trace() -> None:
    event = parse_signal_generate_line(TRACE_LINE)

    assert event is not None
    assert event.sender_comm == "postgres-sender"
    assert event.sender_host_pid == 4210
    assert event.target_host_pid == 54909
    assert event.signal == 3
    assert parse_signal_generate_line(TRACE_LINE.replace("sig=3", "sig=15")) is None
    with pytest.raises(ValueError, match="fields_missing"):
        parse_signal_generate_line(TRACE_LINE.replace(" res=0", ""))


def test_reads_host_to_container_namespace_pid_chain(tmp_path: Path) -> None:
    status = tmp_path / "54909" / "status"
    status.parent.mkdir(parents=True)
    status.write_text("Name:\tpostgres\nNSpid:\t54909\t204\n", encoding="utf-8")

    assert read_namespace_pids(54909, proc_root=tmp_path) == (54909, 204)


def test_evidence_store_never_overwrites_and_fails_closed_at_64_events(
    tmp_path: Path,
) -> None:
    store = ObserverEvidenceStore(tmp_path)
    receipts = [store.append_event({"index": index}) for index in range(64)]

    assert len({receipt["event_path"] for receipt in receipts}) == 64
    assert store.usage()["event_count"] == 64
    with pytest.raises(EvidenceCapacityExhausted, match="count_budget"):
        store.append_event({"index": 65})


def test_signal_target_contract_is_exact_single_use_and_mode_0600(
    tmp_path: Path,
) -> None:
    store = ObserverEvidenceStore(tmp_path)

    store.write_signal_target(postgres_pid=204, host_pid=54909)

    assert store.signal_target_path.stat().st_mode & 0o777 == 0o600
    assert store.consume_signal_target(12) is None
    assert store.signal_target_path.exists()
    assert store.consume_signal_target(54909) == 204
    assert not store.signal_target_path.exists()


def test_tracefs_instance_uses_only_owned_instance_and_exact_filter(
    tmp_path: Path,
) -> None:
    global_event = tmp_path / "events" / "signal" / "signal_generate"
    instance = TraceFsInstance(tmp_path)
    global_event.mkdir(parents=True)
    instance.event_root.mkdir(parents=True)
    for path in (
        instance.instance_root / "tracing_on",
        instance.instance_root / "trace",
        instance.event_root / "enable",
        instance.event_root / "filter",
    ):
        path.write_text("", encoding="utf-8")

    actual_filter = instance.prepare()

    assert actual_filter == 'sig == 3 && comm == "postgres"'
    assert (instance.instance_root / "tracing_on").read_text() == "1"
    assert (instance.event_root / "enable").read_text() == "1"
    assert not (tmp_path / "tracing_on").exists()


class _FakeCursor:
    def __init__(self) -> None:
        self.description = []
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, command: str) -> None:
        columns = [
            "type",
            "user",
            "database",
            "addr",
            "remote_pid",
            "application_name",
            "ptr",
            "link",
        ]
        self.description = [SimpleNamespace(name=name) for name in columns]
        if command == "SHOW SERVERS":
            self._rows = [
                (
                    "S",
                    "mindscape",
                    "mindscape_core",
                    "postgres",
                    204,
                    "",
                    "0xserver",
                    "0xclient",
                )
            ]
        elif command == "SHOW CLIENTS":
            self._rows = [
                (
                    "C",
                    "mindscape",
                    "mindscape_core",
                    "172.20.0.4",
                    4242,
                    "local-core-backend:core",
                    "0xclient",
                    "0xserver",
                )
            ]
        else:
            raise AssertionError(command)

    def fetchall(self):
        return self._rows


class _FakeConnection:
    autocommit = False

    def cursor(self):
        return _FakeCursor()

    def close(self) -> None:
        pass


def test_pgbouncer_correlation_returns_only_bounded_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.pgbouncer.psycopg2.connect",
        lambda *args, **kwargs: _FakeConnection(),
    )
    client = PgBouncerCorrelationClient(
        "postgresql://user:secret@pgbouncer:6432/pgbouncer"
    )

    result = client.correlate(204)
    serialized = json.dumps(result, sort_keys=True)

    assert result["application_name"] == "local-core-backend:core"
    assert result["client_remote_pid"] == 4242
    assert result["client_remote_pid_available"] is True
    assert result["postgres_remote_pid"] == 204
    assert result["client_address_class"] == "private"
    assert "mindscape" not in result["user_sha256"]
    assert "secret" not in serialized
    assert "SELECT" not in serialized


def test_pgbouncer_correlation_uses_exact_source_owned_application_identity(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.pgbouncer.psycopg2.connect",
        lambda *args, **kwargs: _FakeConnection(),
    )
    monkeypatch.setattr(
        _FakeCursor,
        "fetchall",
        lambda self: [
            tuple("" if index == 5 else value for index, value in enumerate(row))
            for row in self._rows
        ],
    )
    client = PgBouncerCorrelationClient(
        "postgresql://user:secret@pgbouncer:6432/pgbouncer",
        expected_application_name="postgres-signal-observer-drill-client",
    )

    result = client.correlate(204)

    assert result["application_name"] == "postgres-signal-observer-drill-client"


class _TcpFakeCursor(_FakeCursor):
    def execute(self, command: str) -> None:
        super().execute(command)
        if command == "SHOW CLIENTS":
            self._rows = [
                tuple(0 if index == 4 else value for index, value in enumerate(row))
                for row in self._rows
            ]


class _TcpFakeConnection(_FakeConnection):
    def cursor(self):
        return _TcpFakeCursor()


def test_pgbouncer_correlation_marks_tcp_client_pid_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.pgbouncer.psycopg2.connect",
        lambda *args, **kwargs: _TcpFakeConnection(),
    )
    client = PgBouncerCorrelationClient(
        "postgresql://user:secret@pgbouncer:6432/pgbouncer",
        expected_application_name="local-core-backend:core",
    )

    result = client.correlate(204)

    assert result["status"] == "correlated"
    assert result["client_remote_pid_available"] is False
    assert result["client_remote_pid"] == 0
    assert result["postgres_remote_pid"] == 204


@pytest.mark.parametrize(
    ("available", "client_pid"),
    ((True, 0), (False, 4242), (1, 4242)),
)
def test_pgbouncer_correlation_rejects_inconsistent_client_pid_availability(
    available: object,
    client_pid: int,
) -> None:
    payload = {
        "status": "correlated",
        "application_name": "postgres-signal-observer-drill-client",
        "database": "mindscape_core",
        "user_sha256": "d" * 64,
        "client_address_class": "private",
        "client_remote_pid_available": available,
        "client_remote_pid": client_pid,
        "postgres_remote_pid": 204,
    }

    with pytest.raises(RuntimeError, match="pgbouncer_correlation_projection_invalid"):
        validate_pgbouncer_correlation(payload, target_postgres_pid=204)


def _config(tmp_path: Path) -> ObserverConfig:
    repo_root = Path(__file__).resolve().parents[3]
    return ObserverConfig(
        evidence_root=tmp_path / "observer",
        journal_root=tmp_path / "journal",
        pgbouncer_admin_url="postgresql://user:secret@pgbouncer:6432/pgbouncer",
        artifact_sha256=canonical_observer_artifact_sha256(repo_root),
        source_commit="0123456789abcdef",
        image_digest="sha256:" + "d" * 64,
        repo_root=repo_root,
        trace_root=tmp_path / "trace",
    )


def _set_observer_identity_environment(
    monkeypatch: pytest.MonkeyPatch,
    config: ObserverConfig,
) -> None:
    monkeypatch.setenv(
        "POSTGRES_SIGNAL_OBSERVER_EVIDENCE_DIR",
        str(config.evidence_root),
    )
    monkeypatch.setenv(
        "POSTGRES_SIGNAL_OBSERVER_ARTIFACT_SHA256",
        config.artifact_sha256,
    )
    monkeypatch.setenv(
        "POSTGRES_SIGNAL_OBSERVER_SOURCE_COMMIT",
        config.source_commit,
    )
    monkeypatch.setenv(
        "POSTGRES_SIGNAL_OBSERVER_IMAGE_DIGEST",
        config.image_digest,
    )


def test_signal_event_is_persisted_before_correlation_failure_closes_health(
    tmp_path: Path,
    monkeypatch,
) -> None:
    recorded = []
    config = _config(tmp_path)
    store = ObserverEvidenceStore(config.evidence_root)
    observer = PostgresSignalObserver(
        config,
        store=store,
        trace=SimpleNamespace(instance_name="test", cleanup=lambda: None),
        correlation=SimpleNamespace(
            correlate=lambda pid: (_ for _ in ()).throw(RuntimeError("link gone"))
        ),
    )
    observer._diagnostic_incident_id = "incident-fixture"
    observer._diagnostic_permit_id = "permit-fixture"
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service.read_namespace_pids",
        lambda pid: (pid, 204 if pid == 54909 else 300),
    )
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service."
        "record_database_diagnostic_observation",
        lambda *args, **kwargs: recorded.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="correlation_unavailable"):
        observer._process_line(TRACE_LINE)

    assert store.usage()["event_count"] == 1
    event_path = next((config.evidence_root / "events").glob("event-*.json"))
    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["pgbouncer"]["status"] == "correlation_unavailable"
    assert recorded[0][0][0] == "incident-fixture"
    assert recorded[0][1]["observation_code"] == "postgres_sigquit_signal_observed"
    assert recorded[0][1]["evidence"]["event_context"] == "live_runtime"


def test_postmaster_fanout_is_recorded_once_without_target_correlation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = []
    config = _config(tmp_path)
    store = ObserverEvidenceStore(config.evidence_root)
    clock = iter((10.0, 11.0))
    observer = PostgresSignalObserver(
        config,
        store=store,
        trace=SimpleNamespace(instance_name="test", cleanup=lambda: None),
        correlation=SimpleNamespace(
            correlate=lambda _pid: (_ for _ in ()).throw(
                AssertionError("postmaster fan-out must not query PgBouncer")
            )
        ),
        monotonic=lambda: next(clock),
    )
    observer._diagnostic_incident_id = "incident-fixture"
    observer._diagnostic_permit_id = "permit-fixture"
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service.read_namespace_pids",
        lambda pid: (pid, 1 if pid == 4210 else 204),
    )
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service."
        "record_database_diagnostic_observation",
        lambda *args, **kwargs: recorded.append((args, kwargs)),
    )

    observer._process_line(POSTMASTER_FANOUT_TRACE_LINE)
    observer._process_line(POSTMASTER_FANOUT_TRACE_LINE)

    assert store.usage()["event_count"] == 1
    event_path = next((config.evidence_root / "events").glob("event-*.json"))
    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["signal_origin"] == "postmaster_crash_fanout"
    assert event["pgbouncer"]["status"] == "correlation_unavailable"
    assert len(recorded) == 1
    assert recorded[0][1]["evidence"]["signal_origin"] == (
        "postmaster_crash_fanout"
    )


def test_signal_target_handoff_survives_backend_proc_exit_and_correlates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = []
    config = _config(tmp_path)
    store = ObserverEvidenceStore(config.evidence_root)
    correlation = {
        "status": "correlated",
        "application_name": "postgres-signal-observer-drill-client",
        "database": "mindscape_core",
        "user_sha256": "d" * 64,
        "client_address_class": "private",
        "client_remote_pid_available": True,
        "client_remote_pid": 4242,
        "postgres_remote_pid": 204,
    }
    store.write_signal_target(
        postgres_pid=204,
        host_pid=54909,
        correlation=correlation,
    )
    observer = PostgresSignalObserver(
        config,
        store=store,
        trace=SimpleNamespace(instance_name="test", cleanup=lambda: None),
        correlation=SimpleNamespace(
            correlate=lambda _pid: (_ for _ in ()).throw(
                AssertionError("pre-signal correlation must be consumed")
            )
        ),
    )
    observer._diagnostic_incident_id = "incident-fixture"
    observer._diagnostic_permit_id = "permit-fixture"
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service.read_namespace_pids",
        lambda _pid: (_ for _ in ()).throw(RuntimeError("process exited")),
    )
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service."
        "record_database_diagnostic_observation",
        lambda *args, **kwargs: recorded.append((args, kwargs)),
    )

    observer._process_line(TRACE_LINE)

    event_path = next((config.evidence_root / "events").glob("event-*.json"))
    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["target_namespace_pids"] == [54909, 204]
    assert event["target_postgres_pid"] == 204
    assert event["pgbouncer"] == correlation
    assert not store.signal_target_path.exists()
    assert recorded[0][1]["permit_id"] == "permit-fixture"
    assert recorded[0][1]["evidence"]["event_context"] == "live_runtime"


def test_isolated_observer_marks_events_as_drill_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = []
    config = replace(
        _config(tmp_path),
        expected_application_name="postgres-signal-observer-drill-client",
    )
    observer = PostgresSignalObserver(
        config,
        trace=SimpleNamespace(instance_name="test", cleanup=lambda: None),
        correlation=SimpleNamespace(
            correlate=lambda _pid: {
                "status": "correlated",
                "application_name": "postgres-signal-observer-drill-client",
                "database": "mindscape_core",
                "user_sha256": "d" * 64,
                "client_address_class": "private",
                "client_remote_pid_available": True,
                "client_remote_pid": 4242,
                "postgres_remote_pid": 204,
            }
        ),
    )
    observer._diagnostic_incident_id = "incident-fixture"
    observer._diagnostic_permit_id = "permit-fixture"
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service.read_namespace_pids",
        lambda pid: (pid, 204 if pid == 54909 else 300),
    )
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service."
        "record_database_diagnostic_observation",
        lambda *args, **kwargs: recorded.append((args, kwargs)),
    )

    observer._process_line(TRACE_LINE)

    assert recorded[0][1]["evidence"]["event_context"] == "isolated_drill"


def test_observer_refuses_tracefs_before_exact_incident_permit(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    RuntimeDatabaseIncidentJournal(config.journal_root).open_incident(
        failure_code="postgres_server_closed_unexpectedly"
    )

    class _Trace:
        instance_name = "test"
        prepared = False

        def prepare(self):
            self.prepared = True
            return ""

        def cleanup(self):
            pass

    trace = _Trace()
    observer = PostgresSignalObserver(
        config,
        trace=trace,
        correlation=SimpleNamespace(),
    )

    assert observer.run() == 2
    assert trace.prepared is False
    health = ObserverEvidenceStore(config.evidence_root).read_health()
    assert health["ready"] is False
    assert health["state"] == "fail_closed_observer_error"


def test_observer_refuses_permit_bound_to_another_source_commit(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    journal = RuntimeDatabaseIncidentJournal(config.journal_root)
    incident = journal.open_incident(failure_code="observer_source_mismatch_test")
    journal.record_diagnostic_permit(
        incident.incident_id,
        IncidentDiagnosticPermit(
            permit_id="diagnostic-source-mismatch",
            source_commit="f" * 40,
            allowed_operation_keys=(
                "postgres_signal_observer_start@sha256:" + config.artifact_sha256,
            ),
            test_evidence_paths=("evidence/source-mismatch.json",),
            capture_evidence_id="observer-source-mismatch",
            budget_sha256="b" * 64,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            owner="runtime-db-incident-owner",
        ),
    )

    class _Trace:
        prepared = False

        def prepare(self):
            self.prepared = True
            return ""

        def cleanup(self):
            pass

    trace = _Trace()
    observer = PostgresSignalObserver(
        config,
        trace=trace,
        correlation=SimpleNamespace(),
    )

    assert observer.run() == 2
    assert trace.prepared is False
    terminal = ObserverEvidenceStore(config.evidence_root).read_health()
    assert terminal["failure_detail_code"] == "incident_diagnostic_permit_changed"


def test_observer_persists_starting_health_before_tracefs_prepare(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    journal = RuntimeDatabaseIncidentJournal(config.journal_root)
    incident = journal.open_incident(failure_code="isolated_observer_startup_test")
    journal.record_diagnostic_permit(
        incident.incident_id,
        IncidentDiagnosticPermit(
            permit_id="diagnostic-startup-health",
            source_commit=config.source_commit,
            allowed_operation_keys=(
                "postgres_signal_observer_start@sha256:" + config.artifact_sha256,
            ),
            test_evidence_paths=("evidence/observer-startup.json",),
            capture_evidence_id="observer-startup-health-test",
            budget_sha256="b" * 64,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            owner="runtime-db-incident-owner",
        ),
    )
    store = ObserverEvidenceStore(config.evidence_root)
    startup_receipts = []

    class _BlockedTrace:
        instance_name = "test"

        def prepare(self):
            startup_receipts.append(store.read_health())
            raise RuntimeError("tracefs_mount_or_signal_event_unavailable")

        def cleanup(self):
            pass

    observer = PostgresSignalObserver(
        config,
        store=store,
        trace=_BlockedTrace(),
        correlation=SimpleNamespace(),
    )

    assert observer.run() == 2
    assert startup_receipts[0]["ready"] is False
    assert startup_receipts[0]["state"] == "starting"
    assert startup_receipts[0]["startup_phase"] == "tracefs_prepare"
    terminal = store.read_health()
    assert terminal["ready"] is False
    assert terminal["state"] == "fail_closed_observer_error"
    assert terminal["error_code"] == "RuntimeError"
    assert terminal["error_class"] == "RuntimeError"
    assert (
        terminal["failure_detail_code"] == "tracefs_mount_or_signal_event_unavailable"
    )


def test_observer_health_redacts_unclassified_tracefs_exception_detail(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    journal = RuntimeDatabaseIncidentJournal(config.journal_root)
    incident = journal.open_incident(failure_code="isolated_observer_redaction_test")
    journal.record_diagnostic_permit(
        incident.incident_id,
        IncidentDiagnosticPermit(
            permit_id="diagnostic-observer-redaction",
            source_commit=config.source_commit,
            allowed_operation_keys=(
                "postgres_signal_observer_start@sha256:" + config.artifact_sha256,
            ),
            test_evidence_paths=("evidence/observer-redaction.json",),
            capture_evidence_id="observer-redaction-test",
            budget_sha256="b" * 64,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            owner="runtime-db-incident-owner",
        ),
    )

    class _SensitiveFailureTrace:
        instance_name = "test"

        def prepare(self):
            raise RuntimeError("password=fixture-secret")

        def cleanup(self):
            pass

    observer = PostgresSignalObserver(
        config,
        trace=_SensitiveFailureTrace(),
        correlation=SimpleNamespace(),
    )

    assert observer.run() == 2
    terminal = ObserverEvidenceStore(config.evidence_root).read_health()
    assert terminal["error_code"] == "RuntimeError"
    assert terminal["error_class"] == "RuntimeError"
    assert (
        terminal["failure_detail_code"]
        == "observer_error_unclassified_tracefs_prepare"
    )
    assert "fixture-secret" not in json.dumps(terminal, sort_keys=True)


def test_observer_ready_health_write_failure_remains_tracefs_prepare(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    journal = RuntimeDatabaseIncidentJournal(config.journal_root)
    incident = journal.open_incident(failure_code="isolated_observer_health_write_test")
    journal.record_diagnostic_permit(
        incident.incident_id,
        IncidentDiagnosticPermit(
            permit_id="diagnostic-observer-health-write",
            source_commit=config.source_commit,
            allowed_operation_keys=(
                "postgres_signal_observer_start@sha256:" + config.artifact_sha256,
            ),
            test_evidence_paths=("evidence/observer-health-write.json",),
            capture_evidence_id="observer-health-write-test",
            budget_sha256="b" * 64,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            owner="runtime-db-incident-owner",
        ),
    )

    class _ReadyWriteFailureStore:
        def __init__(self) -> None:
            self.delegate = ObserverEvidenceStore(config.evidence_root)

        def write_health(self, payload):
            if payload.get("ready") is True and payload.get("state") == "ready":
                raise RuntimeError("password=fixture-ready-write-secret")
            return self.delegate.write_health(payload)

    open_pipe_calls: list[bool] = []

    class _PreparedTrace:
        instance_name = "test"

        def prepare(self):
            return 'sig == 3 && comm == "postgres"'

        def open_pipe(self):
            open_pipe_calls.append(True)
            raise AssertionError("trace pipe must not open after ready health write failure")

        def cleanup(self):
            pass

    observer = PostgresSignalObserver(
        config,
        store=_ReadyWriteFailureStore(),
        trace=_PreparedTrace(),
        correlation=SimpleNamespace(),
    )

    assert observer.run() == 2
    assert open_pipe_calls == []
    terminal = ObserverEvidenceStore(config.evidence_root).read_health()
    assert (
        terminal["failure_detail_code"]
        == "observer_error_unclassified_tracefs_prepare"
    )
    assert "fixture-ready-write-secret" not in json.dumps(terminal, sort_keys=True)


def test_observer_health_redacts_unclassified_config_exception_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(
        ObserverConfig,
        "validate",
        lambda _self: (_ for _ in ()).throw(
            RuntimeError("password=fixture-config-secret")
        ),
    )
    observer = PostgresSignalObserver(
        config,
        trace=SimpleNamespace(cleanup=lambda: None),
        correlation=SimpleNamespace(),
    )

    assert observer.run() == 2
    terminal = ObserverEvidenceStore(config.evidence_root).read_health()
    assert (
        terminal["failure_detail_code"]
        == "observer_error_unclassified_config_and_permit_validation"
    )
    assert "fixture-config-secret" not in json.dumps(terminal, sort_keys=True)


def test_observer_health_redacts_unclassified_trace_pipe_exception_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    journal = RuntimeDatabaseIncidentJournal(config.journal_root)
    incident = journal.open_incident(failure_code="isolated_observer_runtime_test")
    journal.record_diagnostic_permit(
        incident.incident_id,
        IncidentDiagnosticPermit(
            permit_id="diagnostic-observer-runtime",
            source_commit=config.source_commit,
            allowed_operation_keys=(
                "postgres_signal_observer_start@sha256:" + config.artifact_sha256,
            ),
            test_evidence_paths=("evidence/observer-runtime.json",),
            capture_evidence_id="observer-runtime-test",
            budget_sha256="b" * 64,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            owner="runtime-db-incident-owner",
        ),
    )

    class _PipeContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    class _SensitiveRuntimeTrace:
        instance_name = "test"

        def prepare(self):
            return 'sig == 3 && comm == "postgres"'

        def open_pipe(self):
            return _PipeContext()

        def cleanup(self):
            pass

    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service.select.select",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("password=fixture-runtime-secret")
        ),
    )
    observer = PostgresSignalObserver(
        config,
        trace=_SensitiveRuntimeTrace(),
        correlation=SimpleNamespace(),
    )

    assert observer.run() == 2
    terminal = ObserverEvidenceStore(config.evidence_root).read_health()
    assert (
        terminal["failure_detail_code"]
        == "observer_error_unclassified_trace_pipe_runtime"
    )
    assert "fixture-runtime-secret" not in json.dumps(terminal, sort_keys=True)


def test_observer_exits_and_fails_closed_when_diagnostic_permit_expires(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = replace(_config(tmp_path), heartbeat_seconds=0.02)
    journal = RuntimeDatabaseIncidentJournal(config.journal_root)
    incident = journal.open_incident(failure_code="observer_permit_expiry_test")
    journal.record_diagnostic_permit(
        incident.incident_id,
        IncidentDiagnosticPermit(
            permit_id="diagnostic-observer-expiry",
            source_commit=config.source_commit,
            allowed_operation_keys=(
                "postgres_signal_observer_start@sha256:" + config.artifact_sha256,
            ),
            test_evidence_paths=("evidence/observer-expiry.json",),
            capture_evidence_id="observer-expiry-test",
            budget_sha256="b" * 64,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(milliseconds=80)
            ).isoformat(),
            owner="runtime-db-incident-owner",
        ),
    )
    cleanup_calls: list[bool] = []

    class _PipeContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    class _PreparedTrace:
        instance_name = "test"

        def prepare(self):
            return 'sig == 3 && comm == "postgres"'

        def open_pipe(self):
            return _PipeContext()

        def cleanup(self):
            cleanup_calls.append(True)

    def _quiet_select(_readers, _writers, _errors, timeout):
        time.sleep(max(timeout, 0))
        return ([], [], [])

    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service.select.select",
        _quiet_select,
    )
    observer = PostgresSignalObserver(
        config,
        trace=_PreparedTrace(),
        correlation=SimpleNamespace(),
    )

    assert observer.run() == 2
    terminal = ObserverEvidenceStore(config.evidence_root).read_health()
    assert terminal["ready"] is False
    assert terminal["state"] == "fail_closed_observer_error"
    assert terminal["failure_detail_code"] == "incident_diagnostic_permit_expired"
    assert cleanup_calls == [True]


def test_docker_healthcheck_reads_only_matching_canonical_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    _set_observer_identity_environment(monkeypatch, config)
    store = ObserverEvidenceStore(config.evidence_root)
    canonical = {
        "ready": True,
        "state": "ready",
        "artifact_sha256": config.artifact_sha256,
        "source_commit": config.source_commit,
        "image_digest": config.image_digest,
        "filter": 'sig == 3 && comm == "postgres"',
    }

    store.write_health(canonical)
    assert _healthcheck(30) == 0

    store.write_health({**canonical, "artifact_sha256": "0" * 64})
    assert _healthcheck(30) == 2


def test_facade_writes_starting_health_before_service_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    _set_observer_identity_environment(monkeypatch, config)

    _write_startup_health()

    health = ObserverEvidenceStore(config.evidence_root).read_health()
    assert health["ready"] is False
    assert health["state"] == "starting"
    assert health["startup_phase"] == "config_and_permit_validation"
    assert health["artifact_sha256"] == config.artifact_sha256
    assert health["source_commit"] == config.source_commit
    assert health["image_digest"] == config.image_digest
