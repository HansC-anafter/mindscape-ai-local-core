from backend.app.routes.core.cli_token import (
    _can_shadow_host_session_candidate,
    _clear_stale_shadow_marker,
    _effective_host_session_pool_enabled,
    _stable_host_session_runtime_id,
)


def test_managed_seed_cannot_shadow_plain_host_runtime_from_another_workspace():
    candidate_metadata = {
        "HOME": "/Users/shock",
        "last_workspace_id": "workspace-a",
    }

    assert (
        _can_shadow_host_session_candidate(
            candidate_metadata,
            request_workspace_id="workspace-b",
        )
        is False
    )


def test_legacy_token_copy_seed_cannot_shadow_in_same_workspace():
    candidate_metadata = {
        "HOME": "/Users/shock",
        "last_workspace_id": "workspace-a",
        "managed_seed_source_home": "/Users/shock/.codex",
    }

    assert (
        _can_shadow_host_session_candidate(
            candidate_metadata,
            request_workspace_id="workspace-a",
        )
        is False
    )


def test_unvalidated_account_snapshot_does_not_enter_executable_pool():
    metadata = {
        "HOME": "/Users/shock",
        "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
        "account_snapshot": True,
        "login_email": "codex@example.test",
        "codex_pool_health": {
            "seed_kind": "account_snapshot",
            "health_state": "healthy",
        },
    }

    assert (
        _effective_host_session_pool_enabled(
            metadata,
            requested_pool_enabled=True,
        )
        is False
    )


def test_managed_mirror_seed_cannot_enable_pool():
    metadata = {
        "HOME": "/Users/shock",
        "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/mirrors/mirror-a",
        "managed_mirror": True,
        "codex_pool_health": {
            "seed_kind": "managed_mirror",
            "health_state": "healthy",
        },
    }

    assert (
        _effective_host_session_pool_enabled(
            metadata,
            requested_pool_enabled=True,
        )
        is False
    )


def test_real_home_without_codex_home_cannot_enable_pool():
    metadata = {
        "HOME": "/Users/shock",
        "codex_pool_health": {
            "seed_kind": "real_home",
            "health_state": "healthy",
        },
    }

    assert (
        _effective_host_session_pool_enabled(
            metadata,
            requested_pool_enabled=True,
        )
        is False
    )


def test_account_home_with_codex_home_can_enable_pool():
    metadata = {
        "HOME": "/Users/shock",
        "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
        "codex_seed_kind": "account_home",
        "login_email": "codex@example.test",
    }

    assert (
        _effective_host_session_pool_enabled(
            metadata,
            requested_pool_enabled=True,
        )
        is True
    )


def test_managed_seed_cannot_shadow_real_home_workspace_fallback():
    candidate_metadata = {
        "HOME": "/Users/shock",
        "last_workspace_id": "workspace-a",
        "codex_pool_health": {
            "seed_kind": "real_home",
            "health_state": "healthy",
        },
    }

    assert (
        _can_shadow_host_session_candidate(
            candidate_metadata,
            request_workspace_id="workspace-a",
        )
        is False
    )


def test_plain_host_runtime_registration_clears_stale_shadow_marker_when_enabled():
    metadata = {
        "HOME": "/Users/shock",
        "shadowed_by_runtime_id": "runtime-codex_cli-seed",
    }

    assert _clear_stale_shadow_marker(metadata, pool_enabled=True) == {
        "HOME": "/Users/shock"
    }


def test_managed_codex_home_registration_keeps_shadow_marker_metadata():
    metadata = {
        "HOME": "/Users/shock",
        "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
        "shadowed_by_runtime_id": "runtime-codex_cli-seed",
    }

    assert _clear_stale_shadow_marker(metadata, pool_enabled=True) == metadata


def test_plain_host_runtime_id_is_workspace_scoped():
    runtime_a = _stable_host_session_runtime_id(
        owner_user_id="default-user",
        surface="codex_cli",
        client_id="client-a",
        metadata={"HOME": "/Users/shock"},
        workspace_id="workspace-a",
    )
    runtime_b = _stable_host_session_runtime_id(
        owner_user_id="default-user",
        surface="codex_cli",
        client_id="client-b",
        metadata={"HOME": "/Users/shock"},
        workspace_id="workspace-b",
    )

    assert runtime_a != runtime_b


def test_managed_codex_home_runtime_id_stays_account_scoped():
    metadata = {
        "HOME": "/Users/shock",
        "CODEX_HOME": "/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-a",
    }
    runtime_a = _stable_host_session_runtime_id(
        owner_user_id="default-user",
        surface="codex_cli",
        client_id="client-a",
        metadata=metadata,
        workspace_id="workspace-a",
    )
    runtime_b = _stable_host_session_runtime_id(
        owner_user_id="default-user",
        surface="codex_cli",
        client_id="client-b",
        metadata=metadata,
        workspace_id="workspace-b",
    )

    assert runtime_a == runtime_b
