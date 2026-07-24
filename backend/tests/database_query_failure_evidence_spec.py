from __future__ import annotations

from backend.app.database.query_failure_evidence import QueryFailureEvidenceRecorder


def test_records_only_redacted_unexpected_close_evidence(monkeypatch) -> None:
    recorded = []
    monkeypatch.setattr(
        "backend.app.database.query_failure_evidence_core.recorder.os.getpid",
        lambda: 4242,
    )
    recorder = QueryFailureEvidenceRecorder(
        application_name="local-core-backend:core",
        record_failure=lambda code, **kwargs: recorded.append((code, kwargs)),
        monotonic=lambda: 10.0,
    )
    statement = "SELECT secret_value FROM private_table WHERE token='do-not-persist'"

    assert (
        recorder.observe(
            RuntimeError("server closed the connection unexpectedly"),
            statement=statement,
        )
        is True
    )
    assert len(recorded) == 1
    code, kwargs = recorded[0]
    evidence = kwargs["evidence"]
    serialized = repr(recorded)

    assert code == "postgres_server_closed_unexpectedly"
    assert evidence["application_name"] == "local-core-backend:core"
    assert evidence["database_role"] == "core"
    assert evidence["client_process_pid"] == "4242"
    assert len(evidence["statement_sha256"]) == 64
    assert evidence["statement_bytes"] == str(len(statement.encode("utf-8")))
    assert "secret_value" not in serialized
    assert "do-not-persist" not in serialized
    assert "server closed" not in serialized


def test_deduplicates_same_failure_burst_and_ignores_application_error() -> None:
    recorded = []
    clock = iter((10.0, 11.0, 50.0))
    recorder = QueryFailureEvidenceRecorder(
        application_name="local-core-runner-browser:vector",
        record_failure=lambda code, **kwargs: recorded.append((code, kwargs)),
        monotonic=lambda: next(clock),
        burst_seconds=30,
    )
    close = RuntimeError("server closed the connection unexpectedly")

    assert recorder.observe(close, statement="SELECT 1") is True
    assert recorder.observe(close, statement="SELECT 1") is False
    assert recorder.observe(close, statement="SELECT 1") is True
    assert (
        recorder.observe(
            RuntimeError("duplicate key value violates unique constraint"),
            statement="INSERT private payload",
        )
        is False
    )
    assert len(recorded) == 2
