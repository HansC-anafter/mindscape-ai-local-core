import json
import os
from types import SimpleNamespace

from datetime import datetime, timedelta, timezone

from backend.app.services.codex_pool_health import (
    HEALTH_METADATA_KEY,
    account_snapshot_is_adopted,
    auth_failure_scope_key,
    read_health_metadata,
    stamp_runtime_failure,
)
from backend.app.services.codex_pool_requalification_service import (
    CodexPoolRequalificationService,
)
from backend.app.services.codex_pool_admission_service import CodexPoolAdmissionService
from backend.app.services.codex_pool_service import CodexPoolService
from backend.app.services.codex_runtime_failure_classifier import (
    classify_codex_cli_runtime_failure,
    extract_codex_quota_reset_at,
)
from backend.app.routes.core.cli_token import _prepare_host_session_runtime_metadata


def _runtime(
    runtime_id,
    *,
    health_state="healthy",
    auth_type="host_session",
    seed_kind="real_home",
):
    extra_metadata = {
        HEALTH_METADATA_KEY: {
            "health_state": health_state,
            "seed_kind": seed_kind,
        }
    }
    if seed_kind == "real_home":
        extra_metadata["CODEX_HOME"] = f"/Users/shock/.codex/{runtime_id}"
    if seed_kind == "account_home":
        extra_metadata["CODEX_HOME"] = (
            f"/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-{runtime_id}"
        )
        extra_metadata["login_email"] = f"{runtime_id}@example.test"
    return SimpleNamespace(
        id=runtime_id,
        auth_type=auth_type,
        extra_metadata=extra_metadata,
    )


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


def test_codex_pool_admission_rejects_token_copy_seed():
    decision = CodexPoolAdmissionService(
        runtime_loader=lambda: [
            SimpleNamespace(
                id="runtime-snapshot",
                auth_type="host_session",
                extra_metadata={
                    "account_snapshot": True,
                    HEALTH_METADATA_KEY: {
                        "health_state": "healthy",
                        "seed_kind": "account_snapshot",
                    },
                },
                cooldown_until=None,
            ),
            SimpleNamespace(
                id="runtime-mirror",
                auth_type="host_session",
                extra_metadata={
                    "managed_mirror": True,
                    HEALTH_METADATA_KEY: {
                        "health_state": "healthy",
                        "seed_kind": "managed_mirror",
                    },
                },
                cooldown_until=None,
            ),
        ],
        requalification_runner=lambda: None,
    ).evaluate_execution_admission()

    assert decision.admissible is False
    assert decision.reason == "no_runnable_runtimes"
    assert decision.runnable_runtime_count == 0
    assert decision.candidate_runtime_ids == ()


def test_codex_pool_admission_rejects_unvalidated_account_snapshot_home(tmp_path):
    codex_home = tmp_path / "accounts" / "acct-a"
    codex_home.mkdir(parents=True)
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "account_id": "acct-a",
                    "access_token": "access-a",
                    "refresh_token": "refresh-a",
                },
            }
        ),
        encoding="utf-8",
    )
    decision = CodexPoolAdmissionService(
        runtime_loader=lambda: [
            SimpleNamespace(
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
                cooldown_until=None,
            )
        ],
        requalification_runner=lambda: None,
    ).evaluate_execution_admission()

    assert decision.admissible is False
    assert decision.reason == "no_runnable_runtimes"
    assert decision.runnable_runtime_count == 0
    assert decision.candidate_runtime_ids == ()


def test_codex_pool_admission_rejects_real_home_without_codex_home():
    decision = CodexPoolAdmissionService(
        runtime_loader=lambda: [
            SimpleNamespace(
                id="runtime-missing-home",
                auth_type="host_session",
                extra_metadata={
                    HEALTH_METADATA_KEY: {
                        "health_state": "healthy",
                        "seed_kind": "real_home",
                    }
                },
                cooldown_until=None,
            )
        ],
        requalification_runner=lambda: None,
    ).evaluate_execution_admission()

    assert decision.admissible is False
    assert decision.reason == "no_runnable_runtimes"
    assert decision.runnable_runtime_count == 0
    assert decision.candidate_runtime_ids == ()


def test_codex_pool_selection_filters_quarantined_runtime_rows():
    candidates = [
        {
            "id": "runtime-a",
            "auth_type": "host_session",
            "extra_metadata": {
                HEALTH_METADATA_KEY: {
                    "health_state": "quarantined",
                    "seed_kind": "account_snapshot",
                }
            },
        },
        {
            "id": "runtime-snapshot",
            "auth_type": "host_session",
            "extra_metadata": {
                HEALTH_METADATA_KEY: {
                    "health_state": "healthy",
                    "seed_kind": "account_snapshot",
                }
            },
        },
        {
            "id": "runtime-mirror",
            "auth_type": "host_session",
            "extra_metadata": {
                HEALTH_METADATA_KEY: {
                    "health_state": "healthy",
                    "seed_kind": "managed_mirror",
                }
            },
        },
        {
            "id": "runtime-b",
            "auth_type": "host_session",
            "extra_metadata": {
                "CODEX_HOME": "/Users/shock/.codex/runtime-b",
                HEALTH_METADATA_KEY: {
                    "health_state": "healthy",
                    "seed_kind": "real_home",
                }
            },
        },
    ]

    runnable = CodexPoolService._filter_runnable_candidate_runtime_rows(candidates)

    assert [runtime["id"] for runtime in runnable] == ["runtime-b"]


def test_plain_home_host_sessions_share_one_quota_scope():
    runtimes = [
        SimpleNamespace(
            id="runtime-codex_cli-workspace-a",
            extra_metadata={"HOME": "/Users/shock"},
        ),
        SimpleNamespace(
            id="runtime-codex_cli-workspace-b",
            extra_metadata={"HOME": "/Users/shock"},
        ),
    ]

    assert CodexPoolService._count_distinct_quota_scopes(runtimes) == 1
    assert (
        CodexPoolService._quota_scope_key(runtimes[0])
        == "host_session:/Users/shock"
    )


def test_codex_home_host_sessions_use_account_specific_quota_scope():
    runtimes = [
        SimpleNamespace(
            id="runtime-codex_cli-a",
            extra_metadata={
                "HOME": "/Users/shock",
                "CODEX_HOME": "/Users/shock/.mindscape/codex/accounts/a",
            },
        ),
        SimpleNamespace(
            id="runtime-codex_cli-b",
            extra_metadata={
                "HOME": "/Users/shock",
                "CODEX_HOME": "/Users/shock/.mindscape/codex/accounts/b",
            },
        ),
    ]

    assert CodexPoolService._count_distinct_quota_scopes(runtimes) == 2


def test_codex_account_key_overrides_home_quota_scope():
    runtimes = [
        SimpleNamespace(
            id="runtime-codex_cli-real",
            extra_metadata={
                "HOME": "/Users/shock",
                "CODEX_HOME": "/Users/shock/.codex",
                "account_key": "account-a",
                "quota_scope_key": "home-scope-a",
            },
        ),
        SimpleNamespace(
            id="runtime-codex_cli-managed",
            extra_metadata={
                "HOME": "/Users/shock",
                "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
                "account_key": "account-a",
                "quota_scope_key": "home-scope-b",
            },
        ),
    ]

    assert CodexPoolService._count_distinct_quota_scopes(runtimes) == 1
    assert CodexPoolService._quota_scope_key(runtimes[0]) == "account:account-a"


def test_codex_runtime_account_identity_payload_exposes_login_email():
    identity = CodexPoolService._runtime_account_identity_payload(
        {
            "login_email": "Dev@MindscapeAI.App",
            "auth_account_id": "account-1",
            "auth_chatgpt_user_id": "user-1",
            "account_key": "acct-key",
            "quota_scope_key": "scope-1",
        }
    )

    assert identity == {
        "identity_status": "email_verified",
        "account_label": "dev@mindscapeai.app",
        "login_email": "dev@mindscapeai.app",
        "auth_account_id": "account-1",
        "auth_chatgpt_user_id": "user-1",
        "account_key": "acct-key",
        "quota_scope_key": "scope-1",
    }


def test_codex_quota_reset_time_is_parsed_from_cli_message():
    reset_at = extract_codex_quota_reset_at(
        "You've hit your usage limit. Try again at May 6th, 2026 2:53 AM."
    )

    assert reset_at is not None
    assert reset_at.isoformat() == "2026-05-06T02:53:00+00:00"


def test_codex_failure_classifier_does_not_treat_probe_name_as_quota():
    classification = classify_codex_cli_runtime_failure(
        'Return ONLY valid JSON: {"codex_pool_quota_probe": true}\n'
        "ERROR: unexpected status 400 Bad Request: "
        "{\"detail\":\"The 'gpt-5.5' model requires a newer version of Codex. "
        "Please upgrade to the latest app or CLI and try again.\"}"
    )

    assert classification == {
        "fault_kind": "runtime",
        "error_code": "codex_cli_version_incompatible",
    }


def test_codex_failure_classifier_does_not_treat_trace_ids_as_429_quota():
    classification = classify_codex_cli_runtime_failure(
        "ERROR: Your access token could not be refreshed because your refresh token "
        "was already used. Please log out and sign in again.\n"
        "cf-ray: abc429def-TPE request id: 429f-not-a-status"
    )

    assert classification == {
        "fault_kind": "auth",
        "error_code": "stale_refresh_token",
    }


def test_codex_failure_classifier_marks_deactivated_workspace_separately():
    classification = classify_codex_cli_runtime_failure(
        'unexpected status 402 Payment Required: {"detail":{"code":"deactivated_workspace"}}'
    )

    assert classification == {
        "fault_kind": "auth",
        "error_code": "deactivated_workspace",
    }


def test_codex_auth_refresh_failure_scope_is_runtime_specific():
    scope = auth_failure_scope_key(
        {"account_key": "same-account"},
        error_code="auth_failure",
        runtime_id="runtime-a",
    )

    assert scope == "runtime:runtime-a"


def test_codex_stale_refresh_token_scope_is_runtime_specific():
    scope = auth_failure_scope_key(
        {"account_key": "same-account"},
        error_code="stale_refresh_token",
        runtime_id="runtime-a",
    )

    assert scope == "runtime:runtime-a"


def test_codex_deactivated_workspace_scope_can_be_account_wide():
    scope = auth_failure_scope_key(
        {"account_key": "same-account"},
        error_code="deactivated_workspace",
        runtime_id="runtime-a",
    )

    assert scope == "account:same-account"


def test_codex_failure_classifier_treats_explicit_429_status_as_quota():
    classification = classify_codex_cli_runtime_failure(
        "ERROR: unexpected status 429 Too Many Requests: usage temporarily limited"
    )

    assert classification == {
        "fault_kind": "quota",
        "error_code": "429",
    }


def test_codex_quota_failure_is_cooldown_only_not_quarantine():
    metadata = {
        HEALTH_METADATA_KEY: {
            "health_state": "quarantined",
            "seed_kind": "account_snapshot",
            "last_failure_code": "401",
        }
    }

    updated = stamp_runtime_failure(
        metadata,
        error_code="429",
        auth_type="host_session",
        failure_scope_key="quota:scope-a",
    )

    health = read_health_metadata(updated, auth_type="host_session")
    assert health["health_state"] == "healthy"
    assert health["last_failure_code"] == "429"


def test_codex_auth_failure_code_quarantines_runtime():
    updated = stamp_runtime_failure(
        {
            HEALTH_METADATA_KEY: {
                "health_state": "healthy",
                "seed_kind": "account_snapshot",
            }
        },
        error_code="auth_failure",
        auth_type="host_session",
    )

    health = read_health_metadata(updated, auth_type="host_session")
    assert health["health_state"] == "quarantined"
    assert health["last_failure_code"] == "auth_failure"


def test_codex_host_registration_preserves_auth_fault_on_route_metadata_change():
    existing_metadata = {
        "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
        "account_snapshot": True,
        "account_key": "account-a",
        "login_email": "account-a@example.test",
        "quota_scope_home": "/Users/shock/.codex-old",
        "codex_auth_has_runtime_credentials": True,
        "codex_auth_mtime_ns": "100",
        "codex_auth_size": "2048",
        HEALTH_METADATA_KEY: {
            "health_state": "quarantined",
            "seed_kind": "account_home",
            "last_failure_code": "stale_refresh_token",
            "failure_codex_auth_mtime_ns": "100",
            "failure_codex_auth_size": "2048",
        },
    }
    incoming_metadata = {
        "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
        "account_snapshot": True,
        "account_key": "account-a",
        "login_email": "account-a@example.test",
        "quota_scope_home": "/Users/shock/.codex-current",
        "codex_auth_has_runtime_credentials": True,
        "codex_auth_mtime_ns": "100",
        "codex_auth_size": "2048",
    }

    merged, reset = _prepare_host_session_runtime_metadata(
        existing_metadata=existing_metadata,
        incoming_metadata=incoming_metadata,
    )

    health = read_health_metadata(merged, auth_type="host_session")
    assert reset is False
    assert health["health_state"] == "quarantined"
    assert health["last_failure_code"] == "stale_refresh_token"


def test_codex_host_registration_reopens_auth_fault_after_auth_material_changes():
    existing_metadata = {
        "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
        "account_snapshot": True,
        "account_key": "account-a",
        "login_email": "account-a@example.test",
        "codex_auth_has_runtime_credentials": True,
        "codex_auth_mtime_ns": "100",
        "codex_auth_size": "2048",
        HEALTH_METADATA_KEY: {
            "health_state": "quarantined",
            "seed_kind": "account_home",
            "last_failure_code": "stale_refresh_token",
            "failure_codex_auth_mtime_ns": "100",
            "failure_codex_auth_size": "2048",
        },
    }
    incoming_metadata = {
        "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
        "account_snapshot": True,
        "account_key": "account-a",
        "login_email": "account-a@example.test",
        "codex_auth_has_runtime_credentials": True,
        "codex_auth_mtime_ns": "101",
        "codex_auth_size": "2048",
    }

    merged, reset = _prepare_host_session_runtime_metadata(
        existing_metadata=existing_metadata,
        incoming_metadata=incoming_metadata,
    )

    health = read_health_metadata(merged, auth_type="host_session")
    assert reset is True
    assert health["health_state"] == "healthy"
    assert health["last_failure_code"] is None
    assert health["last_requalification_reason"] == "auth_material_changed"


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
