from types import SimpleNamespace

import pytest

from backend.app.services.executor_route_resolver import ExecutorRouteSelection
from generation_codex_pool_failover_test_support import _DummyMeeting


@pytest.mark.asyncio
async def test_fetch_direct_codex_auth_bundle_rebinds_sticky_runtime_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    pool_calls: list[dict[str, object]] = []
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
                preferred_runtime_id=None,
                requested_workspace_id="ws-123",
                effective_workspace_id="ws-123",
                auth_workspace_id="ws-123",
                source_workspace_id="ws-123",
                selection_reason="workspace_pool",
                trace=({"via": "workspace_pool"},),
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
                "preferred_runtime_id": "runtime-old",
                "allow_runtime_substitution": False,
                "preference_source": "binding_snapshot",
                "binding_runtime_id": "runtime-old",
                "binding_state": "resolved",
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
            pool_calls.append(
                {
                    "preferred_runtime_id": preferred_runtime_id,
                    "allow_runtime_substitution": allow_runtime_substitution,
                }
            )
            if preferred_runtime_id == "runtime-old":
                return {"error": "Preferred Codex runtime unavailable: runtime-old"}
            return {
                "env": {"CODEX_HOME": "/tmp/acct-b"},
                "selected_runtime_id": "runtime-new",
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

    assert pool_calls == [
        {
            "preferred_runtime_id": "runtime-old",
            "allow_runtime_substitution": False,
        },
        {
            "preferred_runtime_id": None,
            "allow_runtime_substitution": True,
        },
    ]
    assert binding_calls == [
        {
            "surface": "codex_cli",
            "resolved_runtime_id": "runtime-new",
            "policy_mode": "pool_rotation",
        },
        {
            "surface": "codex_cli",
            "runtime_id": "runtime-new",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
            "workspace_id": "ws-123",
        },
    ]
    assert bundle["selected_runtime_id"] == "runtime-new"
    assert bundle["preference_source"] == "binding_rebind"

@pytest.mark.asyncio
async def test_fetch_direct_codex_auth_bundle_rebinds_session_lease_when_pool_falls_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    pool_calls: list[dict[str, object]] = []
    binding_calls: list[dict[str, object]] = []

    class _FakeResolver:
        def resolve(self, **kwargs):
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
        def resolve_pool_preference(
            self,
            *,
            selection,
            lease_owner_type=None,
            lease_owner_id=None,
        ):
            return {
                "preferred_runtime_id": "runtime-old",
                "allow_runtime_substitution": True,
                "preference_source": "session_lease",
                "binding_runtime_id": "runtime-old",
                "binding_state": "resolved",
                "lease_runtime_id": "runtime-old",
                "lease_state": "active",
                "lease_owner_type": lease_owner_type,
                "lease_owner_id": lease_owner_id,
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

        def clear_runtime_lease(self, **kwargs):
            raise AssertionError("session lease should rebind in-place, not clear first")

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
            pool_calls.append(
                {
                    "preferred_runtime_id": preferred_runtime_id,
                    "allow_runtime_substitution": allow_runtime_substitution,
                }
            )
            assert preferred_runtime_id == "runtime-old"
            assert allow_runtime_substitution is True
            return {
                "env": {"CODEX_HOME": "/tmp/acct-b"},
                "selected_runtime_id": "runtime-new",
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

    assert pool_calls == [
        {
            "preferred_runtime_id": "runtime-old",
            "allow_runtime_substitution": True,
        }
    ]
    assert bundle["selected_runtime_id"] == "runtime-new"
    assert bundle["preference_source"] == "lease_rebind"
    assert binding_calls == [
        {
            "surface": "codex_cli",
            "resolved_runtime_id": "runtime-new",
            "policy_mode": "pool_rotation",
        },
        {
            "surface": "codex_cli",
            "runtime_id": "runtime-new",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
            "workspace_id": "ws-123",
        },
    ]

@pytest.mark.asyncio
async def test_fetch_direct_codex_auth_bundle_blocks_when_admission_finds_no_healthy_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()

    class _FakeResolver:
        def resolve(self, **kwargs):
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
        def resolve_pool_preference(
            self,
            *,
            selection,
            lease_owner_type=None,
            lease_owner_id=None,
        ):
            return {
                "preferred_runtime_id": None,
                "allow_runtime_substitution": True,
                "preference_source": "pool_rotation",
                "binding_runtime_id": None,
                "binding_state": "configured",
            }

    class _ExplodingPoolService:
        def get_active_auth_bundle(self, **kwargs):
            raise AssertionError("pool selection should not run when admission blocks")

    class _FakeAdmissionDecision:
        admissible = False

        @staticmethod
        def blocker_message():
            return "Codex pool admission blocked: no_healthy_runtimes"

        @staticmethod
        def to_payload():
            return {
                "admissible": False,
                "reason": "no_healthy_runtimes",
                "healthy_runtime_count": 0,
            }

    class _FakeAdmissionService:
        def evaluate_execution_admission(
            self,
            *,
            preferred_runtime_id=None,
            allow_runtime_substitution=True,
            require_probe_available=False,
        ):
            return _FakeAdmissionDecision()

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
        _ExplodingPoolService,
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

    assert bundle["error"] == "Codex pool admission blocked: no_healthy_runtimes"
    assert bundle["admission"]["reason"] == "no_healthy_runtimes"
