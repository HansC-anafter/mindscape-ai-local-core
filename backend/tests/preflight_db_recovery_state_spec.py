from __future__ import annotations

from backend.scripts.preflight_db_core import (
    DatabaseProbeState,
    run_bounded_database_probe,
)


def test_recovery_probe_waits_and_then_returns_ready() -> None:
    attempts = iter(
        [
            RuntimeError("the database system is starting up"),
            RuntimeError("server closed the connection unexpectedly"),
            "ready",
        ]
    )
    now = [0.0]

    def probe():
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    result, value = run_bounded_database_probe(
        probe,
        sleep=lambda delay: now.__setitem__(0, now[0] + delay),
        monotonic=lambda: now[0],
    )

    assert result.state is DatabaseProbeState.READY
    assert result.attempts == 3
    assert value == "ready"


def test_auth_failure_is_not_retried_or_reported_as_schema_missing() -> None:
    result, value = run_bounded_database_probe(
        lambda: (_ for _ in ()).throw(
            RuntimeError("password authentication failed for user mindscape")
        ),
        sleep=lambda _delay: (_ for _ in ()).throw(AssertionError("must not sleep")),
    )

    assert result.state is DatabaseProbeState.AUTH_FAILED
    assert result.attempts == 1
    assert value is None


def test_bounded_probe_stops_at_timeout_without_fabricating_missing_tables() -> None:
    now = [0.0]

    result, _ = run_bounded_database_probe(
        lambda: (_ for _ in ()).throw(RuntimeError("pgbouncer unavailable")),
        timeout_seconds=3,
        delay_schedule=(1, 2),
        sleep=lambda delay: now.__setitem__(0, now[0] + delay),
        monotonic=lambda: now[0],
    )

    assert result.state is DatabaseProbeState.UNAVAILABLE
    assert result.elapsed_seconds == 3
