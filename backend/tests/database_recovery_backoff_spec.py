from __future__ import annotations

from backend.app.database.recovery_backoff import (
    DatabaseFailureCode,
    classify_database_error,
    is_database_recovery_error,
)


def _nested(message: str) -> BaseException:
    try:
        try:
            raise RuntimeError(message)
        except RuntimeError as inner:
            raise RuntimeError("sqlalchemy wrapper") from inner
    except RuntimeError as outer:
        return outer


def test_classifies_unexpected_close_through_nested_exception_chain() -> None:
    classification = classify_database_error(
        _nested("server closed the connection unexpectedly")
    )

    assert classification.code is DatabaseFailureCode.POSTGRES_SERVER_CLOSED_UNEXPECTEDLY
    assert classification.recovery_related is True
    assert classification.opens_incident is True


def test_classifies_startup_read_only_and_pgbouncer_failures() -> None:
    cases = {
        "database system is not yet accepting connections": DatabaseFailureCode.POSTGRES_STARTUP_RECOVERY,
        "cannot execute INSERT in a read-only transaction": DatabaseFailureCode.POSTGRES_READ_ONLY,
        "PgBouncer: query_wait_timeout": DatabaseFailureCode.PGBOUNCER_UNAVAILABLE,
    }

    for message, expected in cases.items():
        classification = classify_database_error(RuntimeError(message))
        assert classification.code is expected
        assert classification.recovery_related is True


def test_application_sql_errors_do_not_enter_recovery_backoff() -> None:
    error = RuntimeError("duplicate key value violates unique constraint")

    assert classify_database_error(error).code is DatabaseFailureCode.SQL_APPLICATION_ERROR
    assert is_database_recovery_error(error) is False
