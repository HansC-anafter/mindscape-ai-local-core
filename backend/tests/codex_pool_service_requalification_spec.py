import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.app.services.codex_pool_health import (
    HEALTH_METADATA_KEY,
    account_snapshot_is_adopted,
    read_health_metadata,
    stamp_runtime_failure,
)
from backend.app.services.codex_pool_requalification_service import (
    CodexPoolRequalificationService,
)


def test_codex_requalification_retires_stale_unvalidated_snapshot():
    runtime = SimpleNamespace(
        id="runtime-codex_cli-stale",
        auth_type="host_session",
        pool_enabled=True,
        cooldown_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        last_error_code="stale_refresh_token",
        extra_metadata={
            "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-stale",
            "account_snapshot": True,
            "login_email": "codex@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "quarantined",
                "seed_kind": "account_snapshot",
                "last_failure_code": "stale_refresh_token",
            },
        },
    )

    summary = CodexPoolRequalificationService()._apply_requalification(
        [runtime],
        now=datetime.now(timezone.utc),
        persist_updates=lambda _: None,
    )

    assert runtime.pool_enabled is False
    assert summary.manual_repair_required_count == 0
    assert summary.manual_repair_runtime_ids == ()
    assert summary.retired_runtime_count == 1
    assert summary.retired_runtime_ids == ("runtime-codex_cli-stale",)


def test_codex_requalification_reopens_stale_refresh_after_auth_material_changes():
    failed_metadata = stamp_runtime_failure(
        {
            "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-live",
            "account_snapshot": True,
            "runtime_probe_validated_at": "2026-05-06T19:00:00+00:00",
            "login_email": "codex@example.test",
            "codex_auth_mtime_ns": "100",
            "codex_auth_size": "2048",
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_home",
            },
        },
        error_code="stale_refresh_token",
        auth_type="host_session",
        failure_scope_key="runtime:runtime-codex_cli-live",
    )
    failed_metadata["codex_auth_mtime_ns"] = "200"
    runtime = SimpleNamespace(
        id="runtime-codex_cli-live",
        auth_type="host_session",
        pool_enabled=True,
        cooldown_until=datetime.now(timezone.utc) + timedelta(minutes=10),
        last_error_code="stale_refresh_token",
        extra_metadata=failed_metadata,
    )

    summary = CodexPoolRequalificationService()._apply_requalification(
        [runtime],
        now=datetime.now(timezone.utc),
        persist_updates=lambda _: None,
    )

    health = read_health_metadata(runtime.extra_metadata, auth_type="host_session")
    assert health["health_state"] == "healthy"
    assert health["last_requalification_reason"] == "stale_auth_scope_replaced"
    assert runtime.cooldown_until is None
    assert runtime.last_error_code is None
    assert summary.requalified_runtime_count == 1


def test_codex_requalification_retries_executable_auth_after_auth_cooldown():
    runtime = SimpleNamespace(
        id="runtime-codex_cli-live",
        auth_type="host_session",
        pool_enabled=True,
        cooldown_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        last_error_code="stale_refresh_token",
        extra_metadata={
            "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-live",
            "account_snapshot": True,
            "runtime_probe_validated_at": "2026-05-06T19:00:00+00:00",
            "login_email": "codex@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "quarantined",
                "seed_kind": "account_home",
                "last_failure_code": "stale_refresh_token",
            },
        },
    )

    summary = CodexPoolRequalificationService()._apply_requalification(
        [runtime],
        now=datetime.now(timezone.utc),
        persist_updates=lambda _: None,
    )

    health = read_health_metadata(runtime.extra_metadata, auth_type="host_session")
    assert health["health_state"] == "healthy"
    assert health["last_failure_code"] is None
    assert health["last_requalification_reason"] == "auth_cooldown_expired_retry"
    assert runtime.last_error_code is None
    assert runtime.cooldown_until is None
    assert summary.requalified_runtime_count == 1
    assert summary.manual_repair_required_count == 0


def test_codex_requalification_keeps_deactivated_workspace_manual():
    runtime = SimpleNamespace(
        id="runtime-codex_cli-deactivated",
        auth_type="host_session",
        pool_enabled=True,
        cooldown_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        last_error_code="deactivated_workspace",
        extra_metadata={
            "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-live",
            "account_snapshot": True,
            "runtime_probe_validated_at": "2026-05-06T19:00:00+00:00",
            "login_email": "codex@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "quarantined",
                "seed_kind": "account_home",
                "last_failure_code": "deactivated_workspace",
            },
        },
    )

    summary = CodexPoolRequalificationService()._apply_requalification(
        [runtime],
        now=datetime.now(timezone.utc),
        persist_updates=lambda _: None,
    )

    health = read_health_metadata(runtime.extra_metadata, auth_type="host_session")
    assert health["health_state"] == "quarantined"
    assert health["last_failure_code"] == "deactivated_workspace"
    assert runtime.last_error_code == "deactivated_workspace"
    assert summary.requalified_runtime_count == 0
    assert summary.manual_repair_required_count == 1
    assert summary.manual_repair_runtime_ids == ("runtime-codex_cli-deactivated",)


def test_legacy_account_home_validated_stamp_does_not_adopt_copied_snapshot(tmp_path):
    account_home = tmp_path / "accounts" / "acct-live"
    account_home.mkdir(parents=True)
    (account_home / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": "redacted-access",
                    "id_token": "redacted-id",
                }
            }
        ),
        encoding="utf-8",
    )
    (account_home / ".mindscape-seed.json").write_text(
        json.dumps(
            {
                "account_snapshot": True,
                "source_home": "/Users/shock/.codex",
                "auth_synced_from_home": "/Users/shock/.codex",
                "auth_synced_at": "2999-01-01T00:00:00+00:00",
                "account_home_validated_at": "2026-05-07T04:20:48+00:00",
                "login_email": "codex@example.test",
            }
        ),
        encoding="utf-8",
    )
    metadata = {
        "CODEX_HOME": str(account_home),
        "account_snapshot": True,
        "login_email": "codex@example.test",
    }

    assert account_snapshot_is_adopted(metadata) is False
    health = read_health_metadata(metadata, auth_type="host_session")
    assert health["seed_kind"] == "account_snapshot"


def test_legacy_bridge_account_home_validated_stamp_does_not_adopt_snapshot():
    metadata = {
        "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-live",
        "account_snapshot": True,
        "seed_source_home": "/Users/shock/.codex",
        "seed_auth_synced_at": "2999-01-01T00:00:00+00:00",
        "account_home_validated_at": "2026-05-07T04:20:48+00:00",
        "login_email": "codex@example.test",
        "codex_auth_has_runtime_credentials": True,
        "codex_auth_mtime_ns": "123",
        "codex_auth_size": "2048",
    }

    assert account_snapshot_is_adopted(metadata) is False
    health = read_health_metadata(metadata, auth_type="host_session")
    assert health["seed_kind"] == "account_snapshot"


def test_codex_requalification_clears_expired_quota_even_when_previous_state_quarantined():
    runtime = SimpleNamespace(
        id="runtime-codex_cli-quota",
        auth_type="host_session",
        cooldown_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        last_error_code="429",
        extra_metadata={
            "CODEX_HOME": "/Users/shock/.codex/runtime-codex_cli-quota",
            HEALTH_METADATA_KEY: {
                "health_state": "quarantined",
                "seed_kind": "real_home",
                "last_failure_code": "429",
            }
        },
    )

    assert (
        CodexPoolRequalificationService._due_action(
            runtime,
            now=datetime.now(timezone.utc),
        )
        == "cooldown_cleared"
    )


def test_codex_requalification_retires_unvalidated_account_snapshot_after_quota():
    runtime = SimpleNamespace(
        id="runtime-codex_cli-snapshot",
        auth_type="host_session",
        pool_enabled=True,
        cooldown_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        last_error_code="429",
        extra_metadata={
            "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
            "account_snapshot": True,
            "login_email": "codex@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_home",
                "last_failure_code": "429",
            }
        },
    )

    assert (
        CodexPoolRequalificationService._due_action(
            runtime,
            now=datetime.now(timezone.utc),
        )
        == "retire_non_executable_seed"
    )


def test_codex_requalification_retires_real_home_without_codex_home():
    runtime = SimpleNamespace(
        id="runtime-codex_cli-missing-home",
        auth_type="host_session",
        pool_enabled=True,
        cooldown_until=None,
        last_error_code=None,
        extra_metadata={
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "real_home",
            }
        },
    )

    assert (
        CodexPoolRequalificationService._due_action(
            runtime,
            now=datetime.now(timezone.utc),
        )
        == "retire_non_executable_seed"
    )


def test_codex_requalification_disables_unvalidated_account_snapshot_pool_member():
    runtime = SimpleNamespace(
        id="runtime-codex_cli-snapshot",
        auth_type="host_session",
        pool_enabled=True,
        cooldown_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        last_error_code="429",
        extra_metadata={
            "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
            "account_snapshot": True,
            "login_email": "codex@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_home",
                "last_failure_code": "429",
            }
        },
    )

    summary = CodexPoolRequalificationService()._apply_requalification(
        [runtime],
        now=datetime.now(timezone.utc),
        persist_updates=lambda _: None,
    )

    assert runtime.pool_enabled is False
    assert runtime.cooldown_until is None
    assert runtime.last_error_code == "legacy_token_copy_seed"
    health = read_health_metadata(runtime.extra_metadata, auth_type="host_session")
    assert health["last_requalification_reason"] == "retired_from_pool"
    assert summary.cooldown_cleared_count == 0
    assert summary.retired_runtime_count == 1
    assert summary.retired_runtime_ids == ("runtime-codex_cli-snapshot",)


def test_codex_runtime_fault_reporter_centralizes_quota_and_binding(monkeypatch):
    from backend.app.services import codex_pool_service as pool_module
    from backend.app.services import executor_binding_service as binding_module
    from backend.app.services.codex_pool_runtime_router import (
        report_codex_pool_runtime_fault_sync,
    )

    calls = {}

    class FakePoolService:
        def report_quota_exhausted(self, runtime_id, *, reset_at=None):
            calls["quota"] = (runtime_id, reset_at)
            return {
                "id": runtime_id,
                "cooldown_until": reset_at.isoformat() if reset_at else None,
                "last_error_code": "429",
            }

    class FakeBindingService:
        def record_runtime_fault(self, *, workspace_id, surface, runtime_id, error_code):
            calls["binding"] = {
                "workspace_id": workspace_id,
                "surface": surface,
                "runtime_id": runtime_id,
                "error_code": error_code,
            }

    monkeypatch.setattr(pool_module, "CodexPoolService", FakePoolService)
    monkeypatch.setattr(binding_module, "ExecutorBindingService", FakeBindingService)

    report = report_codex_pool_runtime_fault_sync(
        runtime_id="runtime-codex_cli-a",
        fault_kind="quota",
        workspace_id="workspace-a",
        error_code="429",
        error_text="You've hit your usage limit. Try again at May 6th, 2026 2:53 AM.",
    )

    assert report["reported"] is True
    assert calls["quota"][0] == "runtime-codex_cli-a"
    assert calls["quota"][1].isoformat() == "2026-05-06T02:53:00+00:00"
    assert calls["binding"] == {
        "workspace_id": "workspace-a",
        "surface": "codex_cli",
        "runtime_id": "runtime-codex_cli-a",
        "error_code": "429",
    }


def test_codex_runtime_fault_reporter_auth_signature_is_shared(monkeypatch):
    from backend.app.services import codex_pool_service as pool_module
    from backend.app.services.codex_pool_runtime_router import (
        report_codex_pool_runtime_fault_sync,
    )

    calls = {}

    class FakePoolService:
        def report_auth_failure(self, runtime_id, *, error_code="401"):
            calls["auth"] = {
                "runtime_id": runtime_id,
                "error_code": error_code,
            }
            return {
                "id": runtime_id,
                "cooldown_until": "2026-05-06T00:00:00+00:00",
                "last_error_code": error_code,
            }

    monkeypatch.setattr(pool_module, "CodexPoolService", FakePoolService)

    report = report_codex_pool_runtime_fault_sync(
        runtime_id="runtime-codex_cli-b",
        fault_kind="auth",
        error_code="401",
    )

    assert report["reported"] is True
    assert calls["auth"] == {
        "runtime_id": "runtime-codex_cli-b",
        "error_code": "401",
    }
