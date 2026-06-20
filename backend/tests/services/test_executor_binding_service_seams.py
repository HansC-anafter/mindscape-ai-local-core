from pathlib import Path
from types import SimpleNamespace

from backend.app.services.executor_binding_service import (
    ExecutorBindingService,
    _BINDINGS_KEY,
)
from backend.app.services.executor_route_resolver import ExecutorRouteSelection


def _selection(selection_reason="workspace_pool", preferred_runtime_id=None):
    return ExecutorRouteSelection(
        surface="codex_cli",
        executor_runtime="codex_cli",
        requested_workspace_id="workspace-a",
        effective_workspace_id="workspace-a",
        preferred_runtime_id=preferred_runtime_id,
        selection_reason=selection_reason,
        auth_workspace_id="workspace-a",
        source_workspace_id="workspace-a",
    )


def _service_with_binding(binding):
    workspace = SimpleNamespace(
        id="workspace-a",
        metadata={_BINDINGS_KEY: {"codex_cli": binding}},
        resolved_executor_runtime="codex_cli",
    )
    return ExecutorBindingService(
        workspace_loader=lambda _workspace_id: workspace,
        workspace_saver=lambda item: item,
    )


def test_legacy_module_keeps_public_facade_and_binding_key():
    assert ExecutorBindingService
    assert _BINDINGS_KEY == "executor_route_bindings"


def test_pool_rotation_semantics_stay_fail_closed_for_current_policy():
    service = _service_with_binding(
        {
            "executor_runtime": "codex_cli",
            "preferred_runtime_id": None,
            "concrete_runtime_id": "runtime-codex_cli-previous",
            "binding_state": "resolved",
            "policy_mode": "pool_rotation",
            "selection_reason": "workspace_pool",
            "binding_revision": 3,
        }
    )

    pool_preference = service.resolve_pool_preference(selection=_selection())
    pinned_preference = service.resolve_pool_preference(
        selection=_selection(selection_reason="workspace_default")
    )

    assert pool_preference["preferred_runtime_id"] is None
    assert pool_preference["allow_runtime_substitution"] is True
    assert pool_preference["preference_source"] == "pool_rotation"
    assert pool_preference["binding_runtime_id"] == "runtime-codex_cli-previous"
    assert pinned_preference["preferred_runtime_id"] == "runtime-codex_cli-previous"
    assert pinned_preference["allow_runtime_substitution"] is False
    assert pinned_preference["preference_source"] == "binding_snapshot"


def test_matching_session_lease_keeps_owner_sticky_without_new_store_paths():
    service = _service_with_binding(
        {
            "executor_runtime": "codex_cli",
            "concrete_runtime_id": "runtime-codex-a",
            "binding_state": "resolved",
            "binding_revision": 5,
            "lease_state": "active",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
            "lease_runtime_id": "runtime-codex-b",
        }
    )

    preference = service.resolve_pool_preference(
        selection=_selection(selection_reason="workspace_binding"),
        lease_owner_type="meeting_session",
        lease_owner_id="sess-123",
    )

    assert preference["preferred_runtime_id"] == "runtime-codex-b"
    assert preference["allow_runtime_substitution"] is False
    assert preference["preference_source"] == "session_lease"
    assert preference["lease_runtime_id"] == "runtime-codex-b"


def test_helper_sources_do_not_define_duplicate_resource_paths():
    service_root = Path(__file__).resolve().parents[2] / "app" / "services"
    helper_paths = [
        service_root / "executor_binding_metadata.py",
        service_root / "executor_binding_pool_preference.py",
        service_root / "executor_binding_leases.py",
    ]
    disallowed_markers = [
        "APIRouter",
        "router =",
        "@router",
        "create_engine",
        "sessionmaker",
        "psycopg2",
        "PgBouncer",
        "aiohttp",
        "httpx",
        "requests.",
        "ClientSession",
        "subprocess",
        "Thread(",
        "Process(",
        "setInterval",
        "polling",
        "retry(",
    ]

    for path in helper_paths:
        text = path.read_text(encoding="utf-8")
        assert "class ExecutorBindingService" not in text
        assert "PostgresWorkspacesStore" not in text
        for marker in disallowed_markers:
            assert marker not in text
