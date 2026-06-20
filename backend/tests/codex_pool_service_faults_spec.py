from types import SimpleNamespace

from backend.app.services.codex_pool_health import (
    HEALTH_METADATA_KEY,
    auth_failure_scope_key,
    read_health_metadata,
    stamp_runtime_failure,
)
from backend.app.services.codex_pool_admission_service import CodexPoolAdmissionService
from backend.app.services.codex_pool_service import CodexPoolService
from backend.app.services.codex_runtime_failure_classifier import (
    classify_codex_cli_runtime_failure,
    extract_codex_quota_reset_at,
)
from backend.app.routes.core.cli_token import _prepare_host_session_runtime_metadata


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
        """{"auth_mode":"chatgpt","tokens":{"account_id":"acct-a","access_token":"access-a","refresh_token":"refresh-a"}}""",
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
    assert CodexPoolService._quota_scope_key(runtimes[0]) == "host_session:/Users/shock"


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


def test_codex_failure_classifier_treats_token_refresh_401_as_auth_failure():
    classification = classify_codex_cli_runtime_failure(
        'runtime_error {"error": "token_refresh_http_401"}'
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
