from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

from backend.app.routes.core.cli_token_core.host_session_metadata import (
    _stable_host_session_runtime_id,
)
from backend.app.routes.core.cli_token_core.host_session_registration import (
    HostSessionRegistrationCoordinator,
)
from backend.app.routes.core.cli_token_core.host_session_shadow import (
    _apply_host_session_shadow,
    _host_session_shadow_candidate_key,
)
from backend.app.routes.core.cli_token_core.schemas import RegisterHostSessionRuntimeRequest


class _Clock:
    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now


def _request(
    *,
    runtime_index: int = 0,
    workspace_index: int = 0,
    seed_seen_at: str = "2026-08-01T13:00:00Z",
    runtime_name: str | None = None,
    pool_group: str = "codex-cli-pool",
    pool_enabled: bool = True,
    pool_priority: int | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> RegisterHostSessionRuntimeRequest:
    metadata = {
        "HOME": "/Users/test",
        "CODEX_HOME": f"/Users/test/.codex-{runtime_index:02d}",
        "account_key": f"account-{runtime_index:02d}",
        "seed_last_seen_at": seed_seen_at,
    }
    metadata.update(extra_metadata or {})
    return RegisterHostSessionRuntimeRequest(
        workspace_id=f"workspace-{workspace_index:02d}",
        surface="codex_cli",
        client_id=f"client-{workspace_index:02d}",
        runtime_name=runtime_name or f"Codex account {runtime_index:02d}",
        pool_group=pool_group,
        pool_enabled=pool_enabled,
        pool_priority=runtime_index if pool_priority is None else pool_priority,
        metadata=metadata,
    )


def _runtime_id(
    request: RegisterHostSessionRuntimeRequest,
    *,
    owner_user_id: str = "owner-a",
) -> str:
    return _stable_host_session_runtime_id(
        owner_user_id=owner_user_id,
        surface=request.surface,
        client_id=request.client_id,
        metadata=request.metadata,
        workspace_id=request.workspace_id,
        explicit_runtime_id=request.runtime_id,
    )


class _Callbacks:
    def __init__(self, *, workspace_count: int = 22) -> None:
        self.full_upserts: list[tuple[str, str]] = []
        self.snapshot_reads: list[tuple[str, str, str]] = []
        self.shadow_reconciliations: list[tuple[str, str, tuple[str, ...]]] = []
        self.candidates = {
            ("/Users/test", f"workspace-{index:02d}"): (
                f"plain-runtime-{index:02d}",
            )
            for index in range(workspace_count)
        }

    def upsert_runtime(
        self,
        *,
        owner_user_id: str,
        request: RegisterHostSessionRuntimeRequest,
        reconcile_shadow: bool,
    ) -> dict[str, Any]:
        assert reconcile_shadow is False
        runtime_id = _runtime_id(request, owner_user_id=owner_user_id)
        self.full_upserts.append((runtime_id, request.workspace_id))
        return {
            "id": runtime_id,
            "runtime_id": runtime_id,
            "owner_user_id": owner_user_id,
            "name": request.runtime_name,
            "metadata": {
                **request.metadata,
                "last_workspace_id": request.workspace_id,
                "last_client_id": request.client_id,
            },
            "pool_group": request.pool_group,
            "pool_enabled": request.pool_enabled,
            "pool_priority": request.pool_priority,
            "updated_at": "2026-08-01T13:00:00Z",
        }

    def list_shadow_candidates(
        self,
        *,
        owner_user_id: str,
        surface: str,
        pool_group: str,
    ) -> dict[tuple[str, str], tuple[str, ...]]:
        self.snapshot_reads.append((owner_user_id, surface, pool_group))
        return self.candidates

    def reconcile_shadow(
        self,
        *,
        owner_user_id: str,
        request: RegisterHostSessionRuntimeRequest,
        runtime_id: str,
        candidate_runtime_ids: tuple[str, ...],
    ) -> bool:
        self.shadow_reconciliations.append(
            (runtime_id, request.workspace_id, candidate_runtime_ids)
        )
        return True


def _register(
    coordinator: HostSessionRegistrationCoordinator,
    callbacks: _Callbacks,
    request: RegisterHostSessionRuntimeRequest,
) -> dict[str, Any]:
    return coordinator.register(
        owner_user_id="owner-a",
        request=request,
        upsert_runtime=callbacks.upsert_runtime,
        list_shadow_candidates=callbacks.list_shadow_candidates,
        reconcile_shadow=callbacks.reconcile_shadow,
    )


def test_bounds_forty_runtimes_across_twenty_two_workspaces() -> None:
    clock = _Clock()
    coordinator = HostSessionRegistrationCoordinator(monotonic=clock)
    callbacks = _Callbacks()

    responses = []
    for workspace_index in range(22):
        for runtime_index in range(40):
            responses.append(
                _register(
                    coordinator,
                    callbacks,
                    _request(
                        runtime_index=runtime_index,
                        workspace_index=workspace_index,
                        seed_seen_at=f"first-{workspace_index}-{runtime_index}",
                    ),
                )
            )

    assert len(responses) == 880
    assert len(callbacks.full_upserts) == 40
    assert len(callbacks.snapshot_reads) == 1
    assert len(callbacks.shadow_reconciliations) == 22
    assert len({response["runtime_id"] for response in responses}) == 40
    assert responses[-1]["metadata"]["last_workspace_id"] == "workspace-21"
    assert responses[-1]["metadata"]["last_client_id"] == "client-21"
    assert responses[-1]["metadata"]["seed_last_seen_at"] == "first-21-39"

    for workspace_index in range(22):
        for runtime_index in range(40):
            _register(
                coordinator,
                callbacks,
                _request(
                    runtime_index=runtime_index,
                    workspace_index=workspace_index,
                    seed_seen_at=f"second-{workspace_index}-{runtime_index}",
                ),
            )

    assert len(callbacks.full_upserts) == 40
    assert len(callbacks.snapshot_reads) == 1
    assert len(callbacks.shadow_reconciliations) == 22

    clock.now = 311.0
    for workspace_index in range(22):
        for runtime_index in range(40):
            _register(
                coordinator,
                callbacks,
                _request(
                    runtime_index=runtime_index,
                    workspace_index=workspace_index,
                ),
            )

    assert len(callbacks.full_upserts) == 80
    assert len(callbacks.snapshot_reads) == 2
    assert len(callbacks.shadow_reconciliations) == 44


@pytest.mark.parametrize(
    ("changed_request"),
    [
        _request(runtime_name="Renamed runtime"),
        _request(pool_group="priority-codex-pool"),
        _request(pool_enabled=False),
        _request(pool_priority=99),
        _request(extra_metadata={"XDG_CONFIG_HOME": "/Users/test/config-b"}),
        _request(extra_metadata={"login_email": "changed@example.test"}),
    ],
)
def test_semantic_changes_write_immediately(
    changed_request: RegisterHostSessionRuntimeRequest,
) -> None:
    coordinator = HostSessionRegistrationCoordinator()
    callbacks = _Callbacks(workspace_count=0)

    _register(coordinator, callbacks, _request())
    _register(coordinator, callbacks, changed_request)

    assert len(callbacks.full_upserts) == 2


def test_workspace_client_and_seen_timestamp_do_not_repeat_full_upsert() -> None:
    coordinator = HostSessionRegistrationCoordinator()
    callbacks = _Callbacks()

    first = _register(coordinator, callbacks, _request(workspace_index=0))
    second = _register(
        coordinator,
        callbacks,
        _request(
            workspace_index=1,
            seed_seen_at="2026-08-01T13:04:59Z",
        ),
    )

    assert len(callbacks.full_upserts) == 1
    assert len(callbacks.shadow_reconciliations) == 2
    assert first["metadata"]["last_workspace_id"] == "workspace-00"
    assert second["metadata"]["last_workspace_id"] == "workspace-01"
    assert second["metadata"]["last_client_id"] == "client-01"
    assert second["metadata"]["seed_last_seen_at"] == "2026-08-01T13:04:59Z"


def test_failed_full_upsert_and_shadow_are_not_cached() -> None:
    coordinator = HostSessionRegistrationCoordinator()
    callbacks = _Callbacks()
    upsert_attempts = 0

    def failing_upsert(**kwargs: Any) -> dict[str, Any]:
        nonlocal upsert_attempts
        upsert_attempts += 1
        if upsert_attempts == 1:
            raise RuntimeError("write failed")
        return callbacks.upsert_runtime(**kwargs)

    request = _request()
    with pytest.raises(RuntimeError, match="write failed"):
        coordinator.register(
            owner_user_id="owner-a",
            request=request,
            upsert_runtime=failing_upsert,
            list_shadow_candidates=callbacks.list_shadow_candidates,
            reconcile_shadow=callbacks.reconcile_shadow,
        )
    coordinator.register(
        owner_user_id="owner-a",
        request=request,
        upsert_runtime=failing_upsert,
        list_shadow_candidates=callbacks.list_shadow_candidates,
        reconcile_shadow=callbacks.reconcile_shadow,
    )
    assert upsert_attempts == 2

    shadow_attempts = 0
    second_coordinator = HostSessionRegistrationCoordinator()

    def failing_shadow(**kwargs: Any) -> bool:
        nonlocal shadow_attempts
        shadow_attempts += 1
        if shadow_attempts == 1:
            raise RuntimeError("shadow failed")
        return callbacks.reconcile_shadow(**kwargs)

    with pytest.raises(RuntimeError, match="shadow failed"):
        second_coordinator.register(
            owner_user_id="owner-a",
            request=request,
            upsert_runtime=callbacks.upsert_runtime,
            list_shadow_candidates=callbacks.list_shadow_candidates,
            reconcile_shadow=failing_shadow,
        )
    second_coordinator.register(
        owner_user_id="owner-a",
        request=request,
        upsert_runtime=callbacks.upsert_runtime,
        list_shadow_candidates=callbacks.list_shadow_candidates,
        reconcile_shadow=failing_shadow,
    )
    assert shadow_attempts == 2


def test_runtime_singleflight_and_cache_bounds() -> None:
    coordinator = HostSessionRegistrationCoordinator(
        runtime_max_entries=2,
        shadow_snapshot_max_entries=1,
        shadow_reconciliation_max_entries=2,
    )
    callbacks = _Callbacks()
    request = _request()

    original_upsert = callbacks.upsert_runtime

    def slow_upsert(**kwargs: Any) -> dict[str, Any]:
        time.sleep(0.01)
        return original_upsert(**kwargs)

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(
            executor.map(
                lambda _: coordinator.register(
                    owner_user_id="owner-a",
                    request=request,
                    upsert_runtime=slow_upsert,
                    list_shadow_candidates=callbacks.list_shadow_candidates,
                    reconcile_shadow=callbacks.reconcile_shadow,
                ),
                range(16),
            )
        )

    assert len(callbacks.full_upserts) == 1
    assert len({response["runtime_id"] for response in responses}) == 1

    for runtime_index in range(5):
        _register(
            coordinator,
            callbacks,
            _request(runtime_index=runtime_index),
        )
    sizes = coordinator.cache_sizes
    assert sizes["runtime"] <= 2
    assert sizes["shadow_snapshot"] <= 1
    assert sizes["shadow_candidate_ids"] <= 1024
    assert sizes["shadow_reconciliation"] <= 2


def test_oversized_shadow_snapshot_is_used_but_not_cached() -> None:
    coordinator = HostSessionRegistrationCoordinator(
        shadow_snapshot_max_candidate_ids=2,
    )
    callbacks = _Callbacks(workspace_count=3)

    _register(coordinator, callbacks, _request(workspace_index=0))
    _register(coordinator, callbacks, _request(workspace_index=1))

    assert len(callbacks.snapshot_reads) == 2
    assert coordinator.cache_sizes["shadow_candidate_ids"] == 0
    assert len(callbacks.shadow_reconciliations) == 2


def test_plain_runtime_refresh_invalidates_shadow_inventory() -> None:
    coordinator = HostSessionRegistrationCoordinator()
    callbacks = _Callbacks()
    managed_request = _request(workspace_index=0)
    plain_request = RegisterHostSessionRuntimeRequest(
        workspace_id="workspace-00",
        surface="codex_cli",
        client_id="plain-client",
        runtime_name="Codex plain host runtime",
        pool_group="codex-cli-pool",
        pool_enabled=True,
        pool_priority=0,
        metadata={"HOME": "/Users/test"},
    )

    _register(coordinator, callbacks, managed_request)
    _register(coordinator, callbacks, plain_request)
    _register(coordinator, callbacks, managed_request)

    assert len(callbacks.snapshot_reads) == 2
    assert len(callbacks.shadow_reconciliations) == 2


def test_shadow_candidate_helper_preserves_existing_eligibility() -> None:
    candidate = SimpleNamespace(
        id="plain-runtime",
        user_id="owner-a",
        auth_type="host_session",
        pool_group="codex-cli-pool",
        extra_metadata={
            "surface": "codex_cli",
            "HOME": "/Users/test",
            "codex_home": "/Users/test/accounts/acct-test",
            "codex_seed_kind": "account_home",
            "login_email": "account@example.test",
            "last_workspace_id": "workspace-00",
        },
    )
    request = _request()

    assert _host_session_shadow_candidate_key(
        candidate,
        owner_user_id="owner-a",
        surface="codex_cli",
        pool_group="codex-cli-pool",
    ) == ("/Users/test", "workspace-00")
    assert _apply_host_session_shadow(
        candidates=[candidate],
        owner_user_id="owner-a",
        request=request,
        runtime_id="managed-runtime",
        pool_group="codex-cli-pool",
    ) is True
    assert candidate.extra_metadata["shadowed_by_runtime_id"] == "managed-runtime"
    assert _apply_host_session_shadow(
        candidates=[candidate],
        owner_user_id="owner-a",
        request=request,
        runtime_id="managed-runtime",
        pool_group="codex-cli-pool",
    ) is False
