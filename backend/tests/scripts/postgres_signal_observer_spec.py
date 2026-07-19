from __future__ import annotations

import json
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
from scripts.maintenance.postgres_signal_observer import _healthcheck


TRACE_LINE = (
    "postgres-sender-4210  [003] .... 12345.678901: signal_generate: "
    "sig=3 errno=0 code=0 comm=postgres pid=54909 grp=0 res=0"
)


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
    assert result["postgres_remote_pid"] == 204
    assert result["client_address_class"] == "private"
    assert "mindscape" not in result["user_sha256"]
    assert "secret" not in serialized
    assert "SELECT" not in serialized


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
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service.read_namespace_pids",
        lambda pid: (pid, 204 if pid == 54909 else 300),
    )
    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.service.record_database_failure",
        lambda *args, **kwargs: recorded.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="correlation_unavailable"):
        observer._process_line(TRACE_LINE)

    assert store.usage()["event_count"] == 1
    event_path = next((config.evidence_root / "events").glob("event-*.json"))
    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["pgbouncer"]["status"] == "correlation_unavailable"
    assert recorded[0][0][0] == "postgres_sigquit_signal_observed"


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
            isolated_drill_id="observer-startup-health-test",
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
            isolated_drill_id="observer-redaction-test",
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
            isolated_drill_id="observer-health-write-test",
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
            isolated_drill_id="observer-runtime-test",
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


def test_docker_healthcheck_reads_only_matching_canonical_journal(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
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
    assert _healthcheck(config, 30) == 0

    store.write_health({**canonical, "artifact_sha256": "0" * 64})
    assert _healthcheck(config, 30) == 2
