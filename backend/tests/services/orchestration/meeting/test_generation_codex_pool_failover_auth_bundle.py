from types import SimpleNamespace

import pytest

from backend.app.services.executor_route_resolver import ExecutorRouteSelection
from generation_codex_pool_failover_test_support import _DummyMeeting


@pytest.mark.asyncio
async def test_fetch_direct_codex_auth_bundle_allows_pool_fallback_for_preferred_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    call_kwargs: dict[str, object] = {}
    binding_calls: list[dict[str, object]] = []

    class _FakeResolver:
        def resolve(self, **kwargs):
            assert kwargs == {
                "surface": "codex_cli",
                "workspace_id": "ws-123",
                "auth_workspace_id": None,
                "source_workspace_id": None,
            }
            return ExecutorRouteSelection(
                surface="codex_cli",
                executor_runtime="codex_cli",
                preferred_runtime_id="runtime-preferred",
                requested_workspace_id="ws-123",
                effective_workspace_id="ws-123",
                auth_workspace_id="ws-123",
                source_workspace_id="ws-123",
                selection_reason="preferred",
                trace=({"via": "preferred"},),
            )

    class _FakeBindingService:
        def resolve_pool_preference(
            self,
            *,
            selection,
            lease_owner_type=None,
            lease_owner_id=None,
        ):
            return {
                "preferred_runtime_id": selection.preferred_runtime_id,
                "allow_runtime_substitution": False,
                "preference_source": "executor_route",
                "binding_runtime_id": None,
                "binding_state": "configured",
            }

        def record_route_resolution(self, *, selection, resolved_runtime_id):
            binding_calls.append(
                {
                    "surface": selection.surface,
                    "resolved_runtime_id": resolved_runtime_id,
                    "policy_mode": selection.policy_mode,
                }
            )
            return None

        def record_runtime_lease(
            self,
            *,
            workspace_id,
            surface,
            runtime_id,
            lease_owner_type,
            lease_owner_id,
        ):
            binding_calls.append(
                {
                    "surface": surface,
                    "runtime_id": runtime_id,
                    "lease_owner_type": lease_owner_type,
                    "lease_owner_id": lease_owner_id,
                    "workspace_id": workspace_id,
                }
            )
            return None

    class _FakePoolService:
        def get_active_auth_bundle(
            self,
            *,
            preferred_runtime_id: str | None = None,
            allow_runtime_substitution: bool = False,
            excluded_runtime_ids=None,
            excluded_quota_scope_keys=None,
            require_probe_available=False,
        ):
            call_kwargs["preferred_runtime_id"] = preferred_runtime_id
            call_kwargs["allow_runtime_substitution"] = allow_runtime_substitution
            return {
                "env": {"CODEX_HOME": "/tmp/acct-b"},
                "selected_runtime_id": "runtime-preferred",
                "available_quota_scope_count": 2,
                "probe_state": "available",
                "last_probe_success_at": "2026-05-08T00:00:00+00:00",
            }

    class _FakeAdmissionService:
        def evaluate_execution_admission(
            self,
            *,
            preferred_runtime_id=None,
            allow_runtime_substitution=True,
            require_probe_available=False,
        ):
            return SimpleNamespace(
                admissible=True,
                to_payload=lambda: {"admissible": True},
            )

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "backend.app.services.executor_route_resolver.ExecutorRouteResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "backend.app.services.executor_binding_service.ExecutorBindingService",
        _FakeBindingService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_service.CodexPoolService",
        _FakePoolService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_admission_service.CodexPoolAdmissionService",
        _FakeAdmissionService,
    )
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._generation.asyncio.to_thread",
        _fake_to_thread,
    )

    bundle = await engine._fetch_direct_codex_auth_bundle()

    assert bundle["selected_runtime_id"] == "runtime-preferred"
    assert bundle["requested_workspace_id"] == "ws-123"
    assert bundle["preference_source"] == "executor_route"
    assert call_kwargs == {
        "preferred_runtime_id": "runtime-preferred",
        "allow_runtime_substitution": False,
    }
    assert binding_calls == [
        {
            "surface": "codex_cli",
            "resolved_runtime_id": "runtime-preferred",
            "policy_mode": "pinned_runtime",
        },
        {
            "surface": "codex_cli",
            "runtime_id": "runtime-preferred",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
            "workspace_id": "ws-123",
        },
    ]

@pytest.mark.asyncio
async def test_fetch_direct_codex_auth_bundle_pins_workspace_pool_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    pool_calls: list[int] = []
    binding_calls: list[dict[str, object]] = []
    lease_state: dict[str, str | None] = {"runtime_id": None}

    class _FakeResolver:
        def resolve(self, **kwargs):
            assert kwargs == {
                "surface": "codex_cli",
                "workspace_id": "ws-123",
                "auth_workspace_id": None,
                "source_workspace_id": None,
            }
            return ExecutorRouteSelection(
                surface="codex_cli",
                executor_runtime="codex_cli",
                preferred_runtime_id=None,
                requested_workspace_id="ws-123",
                effective_workspace_id="ws-123",
                auth_workspace_id="ws-123",
                source_workspace_id="ws-123",
                selection_reason="workspace_pool",
                trace=({"via": "workspace_pool"},),
            )

    class _FakeBindingService:
        def load_binding_snapshot(self, *, workspace_id, surface):
            assert workspace_id == "ws-123"
            assert surface == "codex_cli"
            if not lease_state["runtime_id"]:
                return None
            return {
                "binding_state": "resolved",
                "lease_state": "active",
                "lease_owner_type": "meeting_session",
                "lease_owner_id": "sess-123",
                "lease_runtime_id": lease_state["runtime_id"],
            }

        def resolve_pool_preference(
            self,
            *,
            selection,
            lease_owner_type=None,
            lease_owner_id=None,
        ):
            binding_calls.append(
                {
                    "surface": selection.surface,
                    "preference_source": "pool_rotation",
                    "policy_mode": selection.policy_mode,
                    "lease_owner_type": lease_owner_type,
                    "lease_owner_id": lease_owner_id,
                }
            )
            return {
                "preferred_runtime_id": None,
                "allow_runtime_substitution": True,
                "preference_source": "pool_rotation",
                "binding_runtime_id": None,
                "binding_state": "configured",
            }

        def record_route_resolution(self, *, selection, resolved_runtime_id):
            binding_calls.append(
                {
                    "surface": selection.surface,
                    "resolved_runtime_id": resolved_runtime_id,
                    "policy_mode": selection.policy_mode,
                }
            )
            return None

        def record_runtime_lease(
            self,
            *,
            workspace_id,
            surface,
            runtime_id,
            lease_owner_type,
            lease_owner_id,
        ):
            lease_state["runtime_id"] = runtime_id
            binding_calls.append(
                {
                    "surface": surface,
                    "runtime_id": runtime_id,
                    "lease_owner_type": lease_owner_type,
                    "lease_owner_id": lease_owner_id,
                    "workspace_id": workspace_id,
                }
            )
            return None

    class _FakePoolService:
        def get_active_auth_bundle(
            self,
            *,
            preferred_runtime_id: str | None = None,
            allow_runtime_substitution: bool = False,
            excluded_runtime_ids=None,
            excluded_quota_scope_keys=None,
            require_probe_available=False,
        ):
            pool_calls.append(1)
            assert preferred_runtime_id is None
            assert allow_runtime_substitution is True
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "available_quota_scope_count": 4,
                "probe_state": "available",
                "last_probe_success_at": "2026-05-08T00:00:00+00:00",
            }

    class _FakeAdmissionService:
        def evaluate_execution_admission(
            self,
            *,
            preferred_runtime_id=None,
            allow_runtime_substitution=True,
            require_probe_available=False,
        ):
            return SimpleNamespace(
                admissible=True,
                to_payload=lambda: {"admissible": True},
            )

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "backend.app.services.executor_route_resolver.ExecutorRouteResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "backend.app.services.executor_binding_service.ExecutorBindingService",
        _FakeBindingService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_service.CodexPoolService",
        _FakePoolService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_admission_service.CodexPoolAdmissionService",
        _FakeAdmissionService,
    )
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._generation.asyncio.to_thread",
        _fake_to_thread,
    )

    first = await engine._fetch_direct_codex_auth_bundle()
    second = await engine._fetch_direct_codex_auth_bundle()

    assert first["selected_runtime_id"] == "runtime-a"
    assert second["selected_runtime_id"] == "runtime-a"
    assert len(pool_calls) == 1
    assert binding_calls == [
        {
            "surface": "codex_cli",
            "preference_source": "pool_rotation",
            "policy_mode": "pool_rotation",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
        },
        {
            "surface": "codex_cli",
            "resolved_runtime_id": "runtime-a",
            "policy_mode": "pool_rotation",
        },
        {
            "surface": "codex_cli",
            "runtime_id": "runtime-a",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
            "workspace_id": "ws-123",
        },
    ]
