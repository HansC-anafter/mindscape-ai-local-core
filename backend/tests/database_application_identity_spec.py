from __future__ import annotations

import os

import pytest

from backend.app.database.application_identity import (
    DEFAULT_PROCESS_APPLICATION_NAME,
    application_name_for_role,
)


def test_preserves_process_role_and_database_role(monkeypatch) -> None:
    monkeypatch.setenv("DB_APPLICATION_NAME", "local-core-runner-browser")

    assert application_name_for_role("core") == "local-core-runner-browser:core"
    assert application_name_for_role("vector") == "local-core-runner-browser:vector"


def test_invalid_process_identity_uses_explicit_bounded_default() -> None:
    identity = application_name_for_role(
        "core",
        process_application_name="contains credential=value",
    )

    assert identity == f"{DEFAULT_PROCESS_APPLICATION_NAME}:core"
    assert "credential" not in identity


def test_long_identity_is_stable_and_within_postgres_budget() -> None:
    process_name = "local-core-runner-" + "x" * 100

    first = application_name_for_role(
        "vector-readonly",
        process_application_name=process_name,
    )
    second = application_name_for_role(
        "vector-readonly",
        process_application_name=process_name,
    )

    assert first == second
    assert len(first.encode("ascii")) <= 63


def test_unknown_database_role_is_rejected_without_env_mutation() -> None:
    before = dict(os.environ)

    with pytest.raises(ValueError, match="unsupported_database_application_role"):
        application_name_for_role("arbitrary-request-role")

    assert dict(os.environ) == before
