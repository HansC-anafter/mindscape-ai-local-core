import json
import os
from types import SimpleNamespace

from backend.app.services.codex_pool_health import (
    HEALTH_METADATA_KEY,
    read_health_metadata,
    stamp_runtime_failure,
)
from backend.app.services.codex_pool_admission_service import CodexPoolAdmissionService
from backend.app.services.codex_pool_service import CodexPoolService
from backend.tests.codex_pool_service_support import _runtime


def test_codex_pool_selection_filters_quarantined_runtime_objects():
    candidates = [
        _runtime("runtime-a", health_state="quarantined"),
        _runtime("runtime-b", health_state="healthy"),
        _runtime("runtime-c", health_state="probation"),
    ]

    runnable = CodexPoolService._filter_runnable_candidate_runtimes(candidates)

    assert [runtime.id for runtime in runnable] == ["runtime-b", "runtime-c"]


def test_codex_pool_selection_rejects_token_copy_runtime_objects():
    candidates = [
        _runtime("runtime-real", seed_kind="real_home"),
        _runtime("runtime-account", seed_kind="account_home"),
        _runtime("runtime-snapshot", seed_kind="account_snapshot"),
        _runtime("runtime-mirror", seed_kind="managed_mirror"),
    ]

    runnable = CodexPoolService._filter_runnable_candidate_runtimes(candidates)

    assert [runtime.id for runtime in runnable] == ["runtime-real", "runtime-account"]


def test_codex_pool_selection_can_require_probe_available_for_account_home():
    missing_probe = _runtime("runtime-account-a", seed_kind="account_home")
    available = _runtime("runtime-account-b", seed_kind="account_home")
    available.extra_metadata["probe_state"] = "available"
    available.extra_metadata["last_probe_success_at"] = "2026-05-08T00:00:00+00:00"

    runnable = CodexPoolService._filter_runnable_candidate_runtimes(
        [missing_probe, available],
        require_probe_available=True,
    )

    assert [runtime.id for runtime in runnable] == ["runtime-account-b"]


def test_codex_pool_admission_blocks_probe_required_without_available_probe():
    decision = CodexPoolAdmissionService(
        runtime_loader=lambda: [_runtime("runtime-account-a", seed_kind="account_home")],
        requalification_runner=lambda: None,
    ).evaluate_execution_admission(require_probe_available=True)

    assert decision.admissible is False
    assert decision.reason == "no_probe_available_runtimes"
    assert decision.account_home_candidate_count == 1
    assert decision.probe_available_runtime_count == 0


def test_codex_pool_selection_accepts_account_home_path_without_snapshot_marker():
    candidates = [
        SimpleNamespace(
            id="runtime-account-home",
            auth_type="host_session",
            extra_metadata={
                "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
                "login_email": "account-a@example.test",
                "codex_seed_kind": "account_home",
                HEALTH_METADATA_KEY: {
                    "health_state": "healthy",
                    "seed_kind": "account_home",
                    "last_failure_code": "legacy_token_copy_seed",
                },
            },
        ),
    ]

    runnable = CodexPoolService._filter_runnable_candidate_runtimes(candidates)

    assert [runtime.id for runtime in runnable] == ["runtime-account-home"]


def test_codex_pool_selection_rejects_unvalidated_account_snapshot_with_auth_tokens(tmp_path):
    codex_home = tmp_path / "accounts" / "acct-a"
    codex_home.mkdir(parents=True)
    (codex_home / ".mindscape-seed.json").write_text(
        json.dumps(
            {
                "account_snapshot": True,
                "updated_at": "2026-05-06T19:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "account_id": "acct-a",
                    "refresh_token": "refresh-a",
                },
            }
        ),
        encoding="utf-8",
    )
    runtime = SimpleNamespace(
        id="runtime-snapshot",
        auth_type="host_session",
        extra_metadata={
            "CODEX_HOME": str(codex_home),
            "account_snapshot": True,
            "login_email": "account-a@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_snapshot",
            },
        },
    )

    runnable = CodexPoolService._filter_runnable_candidate_runtimes([runtime])
    health = read_health_metadata(runtime.extra_metadata, auth_type="host_session")

    assert runnable == []
    assert health["seed_kind"] == "account_snapshot"


def test_codex_pool_health_does_not_let_snapshot_flag_bypass_with_account_home_kind():
    health = read_health_metadata(
        {
            "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
            "account_snapshot": True,
            "codex_seed_kind": "account_home",
            "login_email": "account-a@example.test",
        },
        auth_type="host_session",
    )

    assert health["seed_kind"] == "account_snapshot"


def test_codex_pool_health_does_not_let_copied_seed_bypass_with_raw_account_home_kind(
    tmp_path,
):
    source_home = tmp_path / ".codex"
    source_home.mkdir()
    codex_home = tmp_path / "codex-home-pool" / "accounts" / "acct-a"
    codex_home.mkdir(parents=True)
    (codex_home / ".mindscape-seed.json").write_text(
        json.dumps(
            {
                "account_snapshot": True,
                "source_home": str(source_home),
            }
        ),
        encoding="utf-8",
    )

    health = read_health_metadata(
        {
            "CODEX_HOME": str(codex_home),
            "login_email": "account-a@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_home",
            },
        },
        auth_type="host_session",
    )

    assert health["seed_kind"] == "account_snapshot"


def test_codex_pool_health_does_not_let_copied_seed_validation_stamp_adopt_snapshot(
    tmp_path,
):
    source_home = tmp_path / ".codex"
    source_home.mkdir()
    codex_home = tmp_path / "codex-home-pool" / "accounts" / "acct-a"
    codex_home.mkdir(parents=True)
    (codex_home / ".mindscape-seed.json").write_text(
        json.dumps(
            {
                "account_snapshot": True,
                "source_home": str(source_home),
            }
        ),
        encoding="utf-8",
    )

    health = read_health_metadata(
        {
            "CODEX_HOME": str(codex_home),
            "account_snapshot": True,
            "runtime_probe_validated_at": "2026-05-07T10:44:54+00:00",
            "login_email": "account-a@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_home",
            },
        },
        auth_type="host_session",
    )

    assert health["seed_kind"] == "account_snapshot"


def test_codex_pool_health_does_not_validate_copied_snapshot_on_quota_failure(
    tmp_path,
):
    source_home = tmp_path / ".codex"
    source_home.mkdir()
    codex_home = tmp_path / "codex-home-pool" / "accounts" / "acct-a"
    codex_home.mkdir(parents=True)
    (codex_home / ".mindscape-seed.json").write_text(
        json.dumps(
            {
                "account_snapshot": True,
                "source_home": str(source_home),
            }
        ),
        encoding="utf-8",
    )

    metadata = stamp_runtime_failure(
        {
            "CODEX_HOME": str(codex_home),
            "account_snapshot": True,
            "login_email": "account-a@example.test",
            "codex_seed_kind": "account_snapshot",
            "seed_source_home": str(source_home),
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_snapshot",
            },
        },
        error_code="429",
        auth_type="host_session",
        failure_scope_key="quota:account:account-a",
    )

    health = read_health_metadata(metadata, auth_type="host_session")
    assert "runtime_probe_validated_at" not in metadata
    assert health["seed_kind"] == "account_snapshot"


def test_codex_pool_health_adopts_copied_snapshot_after_independent_home_login(
    tmp_path,
):
    source_home = tmp_path / ".codex"
    source_home.mkdir()
    codex_home = tmp_path / "codex-home-pool" / "accounts" / "acct-a"
    codex_home.mkdir(parents=True)
    (codex_home / ".mindscape-seed.json").write_text(
        json.dumps(
            {
                "account_snapshot": True,
                "source_home": str(source_home),
                "auth_synced_at": "2026-05-07T10:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    auth_path = codex_home / "auth.json"
    auth_path.write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"refresh_token": "fresh"}}),
        encoding="utf-8",
    )
    os.utime(auth_path, (1778149800, 1778149800))

    health = read_health_metadata(
        {
            "CODEX_HOME": str(codex_home),
            "account_snapshot": True,
            "runtime_probe_validated_at": "2026-05-07T10:44:54+00:00",
            "login_email": "account-a@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_snapshot",
            },
        },
        auth_type="host_session",
    )

    assert health["seed_kind"] == "account_home"


def test_codex_pool_selection_accepts_registered_account_snapshot_auth_material():
    runtime = SimpleNamespace(
        id="runtime-snapshot",
        auth_type="host_session",
        extra_metadata={
            "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
            "account_snapshot": True,
            "codex_seed_kind": "account_home",
            "login_email": "account-a@example.test",
            "account_key": "account-a",
            "codex_auth_has_runtime_credentials": True,
            "codex_auth_mtime_ns": "123",
            "codex_auth_size": "456",
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_snapshot",
            },
        },
    )

    runnable = CodexPoolService._filter_runnable_candidate_runtimes([runtime])
    health = read_health_metadata(runtime.extra_metadata, auth_type="host_session")

    assert [item.id for item in runnable] == ["runtime-snapshot"]
    assert health["seed_kind"] == "account_home"


def test_codex_pool_selection_accepts_validated_account_snapshot_home(tmp_path):
    codex_home = tmp_path / "accounts" / "acct-a"
    codex_home.mkdir(parents=True)
    (codex_home / ".mindscape-seed.json").write_text(
        json.dumps(
            {
                "account_snapshot": True,
                "updated_at": "2026-05-06T19:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "last_refresh": "2026-05-06T19:05:00+00:00",
                "tokens": {
                    "account_id": "acct-a",
                    "refresh_token": "refresh-a",
                },
            }
        ),
        encoding="utf-8",
    )
    runtime = SimpleNamespace(
        id="runtime-snapshot",
        auth_type="host_session",
        extra_metadata={
            "CODEX_HOME": str(codex_home),
            "account_snapshot": True,
            "runtime_probe_validated_at": "2026-05-06T19:10:00+00:00",
            "login_email": "account-a@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_snapshot",
            },
        },
    )

    runnable = CodexPoolService._filter_runnable_candidate_runtimes([runtime])
    health = read_health_metadata(runtime.extra_metadata, auth_type="host_session")

    assert [item.id for item in runnable] == ["runtime-snapshot"]
    assert health["seed_kind"] == "account_home"


def test_codex_pool_selection_rejects_last_refresh_only_account_snapshot(tmp_path):
    codex_home = tmp_path / "accounts" / "acct-a"
    codex_home.mkdir(parents=True)
    (codex_home / ".mindscape-seed.json").write_text(
        json.dumps(
            {
                "account_snapshot": True,
                "updated_at": "2026-05-06T19:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "last_refresh": "2026-05-06T19:05:00+00:00",
                "tokens": {
                    "account_id": "acct-a",
                    "refresh_token": "refresh-a",
                },
            }
        ),
        encoding="utf-8",
    )
    runtime = SimpleNamespace(
        id="runtime-snapshot",
        auth_type="host_session",
        extra_metadata={
            "CODEX_HOME": str(codex_home),
            "account_snapshot": True,
            "login_email": "account-a@example.test",
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_snapshot",
            },
        },
    )

    runnable = CodexPoolService._filter_runnable_candidate_runtimes([runtime])
    health = read_health_metadata(runtime.extra_metadata, auth_type="host_session")

    assert runnable == []
    assert health["seed_kind"] == "account_snapshot"


def test_codex_pool_selection_rejects_real_home_without_codex_home():
    candidates = [
        _runtime("runtime-real", seed_kind="real_home"),
        SimpleNamespace(
            id="runtime-missing-home",
            auth_type="host_session",
            extra_metadata={
                HEALTH_METADATA_KEY: {
                    "health_state": "healthy",
                    "seed_kind": "real_home",
                }
            },
        ),
    ]

    runnable = CodexPoolService._filter_runnable_candidate_runtimes(candidates)

    assert [runtime.id for runtime in runnable] == ["runtime-real"]
